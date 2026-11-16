"""api.py — LA función principal del colector.

    obtener_datos_sitio(cuerpo, lat, lon, radio) -> dict

Es la única función que la aplicación necesita llamar. Orquesta los módulos
temáticos y devuelve UN diccionario con TODOS los parámetros del reto:

    {
      "metadatos":  {...sitio, fechas, fuentes usadas...},
      "topografia": {elevacion, pendiente, rugosidad, crateres/formaciones},
      "termico":    {temperatura media/max/min, dia_noche, estacional},
      "superficie": {albedo/reflectancia, tipo_roca, minerales, polvo},
      "iluminacion":{fraccion diurna, energia solar, PSR, capas},
      "analogos_tierra": {...opcional...},
      "teselas_para_mapa": {...opcional, URLs WMTS para Leaflet...}
    }

Presupuesto de llamadas HTTP (Luna, caso normal, usar_dtm=True):
    1  catálogo Treks        (todas las capas de una vez; cacheado)
    1  STAC USGS             (tiles Kaguya; cacheado)
    1  descarga tile DTM     (~7 MB, S3 estático; cacheado)  -> topografía
    1  GDS Diviner           (consulta + CSV: térmico + albedo en UNA ida)
    0  GDS LOLA              ¡ni se consulta si el DTM cubre la caja!
    1  PDS Search            (bundles Clementine para minerales)
    ------------------------
    5 llamadas en total      (+2 por capa si con_teselas=True, +~6 con tierra)
    Con usar_dtm=False la topografía vuelve a la vía GDS LOLA clásica
    (2 llamadas GDS LOLA) en paralelo con Diviner.

En Marte no hay LOLA/Diviner (son instrumentos lunares): la topografía sale
del DTM de CTX/HiRISE del STAC vía rasterio (mismo formato de métricas, misma
receta de tile GeoTIFF; política de cobertura relajada a >=50 % porque no
existe GDS de respaldo), y el resto de parámetros de las capas de Mars Trek
(térmico honesto: THEMIS/TES + instrucciones de descarga de ODE; no hay
servicio de temperatura puntual). Presupuesto marciano: 2 llamadas de
catálogo + 1 tile DTM (+2 por capa si con_teselas=True). Sitios sin tiles
controlados (p.ej. Gale) quedan en catálogos con nota_elevacion.

En la TIERRA (rama `tierra-datos-crudos`) el MISMO formato de datos crudos
sale de: Copernicus DEM GLO-30 (tile 1°x1° de AWS público, sin auth,
determinista — 0 llamadas de catálogo), NASA POWER (térmico, 2 peticiones
~2 s), Sentinel-2 L2A (superficie, STAC Earth Search + window reads COG) e
iluminación local (0 llamadas). Presupuesto terrestre frío: ~1 tile de
30-50 MB (cacheado) + 4 ventanas S2 (~13 s cada una, cacheadas como .npz)
+ 2 peticiones POWER; tibio ~3-5 s.
"""

from __future__ import annotations

import threading
from datetime import datetime
from pathlib import Path
from typing import Any

from . import (
    analogos_tierra,
    constantes,
    iluminacion,
    iluminacion_tierra,
    superficie,
    superficie_tierra,
    termico,
    termico_tierra,
    topografia,
    topografia_dtm,
    topografia_tierra,
    utilidades,
)


def _capas_trek(cuerpo: str, projtype: str) -> tuple[list, str]:
    """(capas, texto_de_fuente) del catálogo Treks, tolerante a fallos.

    Se usa tanto en la ruta paralela (dentro de un hilo) como en la serie,
    por eso vive en una función propia: nunca lanza, el error va en el texto.
    El catálogo pasa por la caché de catálogos: tras la primera consulta del
    día responde del disco en milisegundos (ver cache_catalogo.py).
    """
    from nsac.sources import trek
    from . import cache_catalogo

    try:
        capas, _de_cache = cache_catalogo.json_o_red(
            f"treks_{cuerpo}_{projtype}",
            lambda: trek.layers(cuerpo, projtype=projtype))
        return capas, f"Treks ({len(capas)} capas, proyección {projtype})"
    except Exception as exc:
        return [], f"Treks FALLÓ: {exc}"


def _dtm_de_stac(cuerpo: str, bbox_s: tuple, lat: float) -> tuple[Any, str]:
    """(catálogo DTM, texto_de_fuente) del STAC de USGS, tolerante a fallos."""
    try:
        return topografia.dtm_disponibles(cuerpo, bbox_s, lat), "USGS STAC (DTM)"
    except Exception as exc:
        return {"error": str(exc)}, "USGS STAC FALLÓ"


def _dtm_encadenado(cuerpo: str, lat: float, lon: float, radio: float,
                    futuro_stac, aviso) -> dict[str, Any]:
    """Análisis DTM que ESPERA al futuro del STAC y reutiliza sus items.

    Se lanza al pool al mismo tiempo que la búsqueda STAC, pero no la
    repite: al llegar su turno hace .result() del futuro (que para entonces
    ya estará hecho o casi) y arranca con los items en la mano. Si el STAC
    falló, devuelve un dict de error con fallback (a la vía GDS en la Luna;
    a 'sin dato puntual' en Marte, donde no existe LOLA).
    """
    try:
        items, _fuente = futuro_stac.result()
    except Exception as exc:
        return {"error": f"STAC falló: {exc}",
                "fallback": "lolardr" if cuerpo == "moon" else "sin_dato_puntual"}
    if isinstance(items, dict) and "error" in items:
        return {"error": f"STAC falló: {items['error']}",
                "fallback": "lolardr" if cuerpo == "moon" else "sin_dato_puntual"}
    return topografia_dtm.analizar_sitio(lat, lon, radio, items_stac=items,
                                         aviso=aviso, cuerpo=cuerpo)


def _aviso(aviso, mensaje: str) -> None:
    """Informa del avance si el llamador pasó una función `aviso` (p.ej. print).

    Las etapas GDS tardan VARIOS MINUTOS en el servidor de PDS (genera los
    CSV a mano alzada): sin estos avisos el programa parece colgado.
    """
    if callable(aviso):
        try:
            aviso(mensaje)
        except Exception:
            pass  # un aviso nunca debe romper la consulta


# Lock del registro: `guardar_en_registro` hace leer-modificar-escribir del
# JSON entero y puede llamarse desde VARIOS hilos a la vez (el pool de
# api.py, o cargadores que lanzan consultas en paralelo). Sin lock, dos
# escrituras simultáneas se pisan (último escritor gana) y se PIERDEN
# entradas ya guardadas — pasó de verdad en la carga masiva de sitios
# (rama `supabase-candidatos`): dos entradas del registro desaparecieron.
# El lock serializa la sección crítica; las consultas siguen en paralelo.
_LOCK_REGISTRO = threading.Lock()


def guardar_en_registro(resultado: dict[str, Any],
                        ruta: str | None = None) -> Any:
    """Guarda la consulta en el registro `colector_datos/data/registro_sitios.json`.

    El registro es un JSON con una entrada POR SITIO (la clave incluye
    cuerpo, lat, lon y radio, p.ej. 'moon@-89.9,0.05±0.05'), así que si
    consultas dos veces el mismo sitio se ACTUALIZA su entrada (nueva fecha,
    mismos datos refrescados) en lugar de acumular duplicados.

    Cada entrada guarda:
      - 'fecha_consulta': cuándo se pidió.
      - 'resumen': los números principales con nombre y unidad, para mirar
        la base de sitios de un vistazo sin abrir el dict completo.
      - 'datos_completos': el diccionario entero (sin la lista cruda de
        puntos LOLA, que se queda resumida en n_puntos).

    Devuelve la ruta del registro. Nunca lanza error: si no se puede escribir
    (permisos, disco), devuelve el detalle del fallo y la consulta sigue.
    """
    ruta = Path(ruta or constantes.RUTA_REGISTRO)
    m = resultado.get("metadatos", {})
    clave = (f"{m.get('cuerpo')}@{m.get('lat')},{m.get('lon')}"
             f"±{m.get('radio_grados')}")

    # Sección crítica (leer-modificar-escribir del JSON entero): el lock
    # evita que dos escritores concurrentes se pisen y pierdan entradas
    # (pasó de verdad en la carga masiva: ver _LOCK_REGISTRO arriba).
    with _LOCK_REGISTRO:
        return _guardar_en_registro_bajo_lock(resultado, ruta, clave, m)


def _guardar_en_registro_bajo_lock(resultado: dict[str, Any], ruta, clave: str,
                                   m: dict[str, Any]) -> Any:
    """Cuerpo de guardar_en_registro (con _LOCK_REGISTRO ya tomado)."""
    import json
    import os
    import shutil

    # Copia ligera: mismo dict, sin los puntos crudos (ya están resumidos).
    copia = json.loads(json.dumps(resultado, default=str))  # deep-copy barato
    copia.get("topografia", {}).pop("puntos", None)

    # Cargar lo que ya había (o arrancar un registro nuevo con una nota).
    registro: dict[str, Any] = {}
    if ruta.exists():
        try:
            registro = json.loads(ruta.read_text(encoding="utf-8"))
        except Exception:
            registro = {}  # JSON corrupto: se rehace (el anterior era cache)
    registro.setdefault(
        "_descripcion",
        "Registro de consultas de obtener_datos_sitio() — NSAC. Clave = "
        "cuerpo@lat,lon±radio; 'resumen' son los números con unidad y "
        "'datos_completos' el dict entero.")

    registro[clave] = {
        "fecha_consulta": m.get("consulta"),
        "resumen": _resumen_para_registro(resultado),
        "datos_completos": copia,
    }

    ruta.parent.mkdir(parents=True, exist_ok=True)
    # Escritura segura: se escribe a un temporal (con el PID en el nombre,
    # para que dos consultas simultáneas no pisen el mismo archivo) y se
    # reemplaza, para no dejar el registro corrupto a medias si el programa
    # se corta.
    temporal = ruta.with_suffix(f".{os.getpid()}.tmp")
    temporal.write_text(json.dumps(registro, indent=2, ensure_ascii=False),
                        encoding="utf-8")
    shutil.move(str(temporal), str(ruta))
    return ruta


def _resumen_para_registro(resultado: dict[str, Any]) -> dict[str, Any]:
    """Extrae los números principales del dict, con nombre y unidad claros.

    Solo coge los valores que existan: un sitio sin GDS o con alguna fuente
    caída simplemente no aporta esas claves al resumen.
    """
    topo = resultado.get("topografia", {})
    term = resultado.get("termico", {})
    sup = resultado.get("superficie", {})
    ilu = resultado.get("iluminacion", {})

    def media(seccion: dict, clave: str) -> Any:
        valor = (seccion or {}).get(clave)
        return valor.get("media") if isinstance(valor, dict) else None

    dia_noche = term.get("dia_noche") or {}
    estacional = term.get("variacion_estacional") or {}
    energia = ilu.get("energia_solar") or {}

    resumen: dict[str, Any] = {
        "elevacion_media_m": media(topo, "elevacion_m"),
        "pendiente_media_grados": media(topo, "pendiente"),
        "rugosidad_media_m": media(topo, "rugosidad"),
        "temperatura_media_k": media(term, "temperatura_superficial"),
        "diferencia_dia_noche_k": dia_noche.get("diferencia_k"),
        "variacion_estacional_k": estacional.get("variacion_k"),
        "reflectancia_media": media(sup, "reflectancia_albedo"),
        "energia_solar_media_wm2": energia.get("energia_media_estimada_wm2"),
        "fraccion_diurna": ilu.get("fraccion_diurna_observada"),
        "n_puntos_lola": topo.get("elevacion_m", {}).get("n")
        if isinstance(topo.get("elevacion_m"), dict) else None,
        "n_observaciones_diviner": term.get("n_observaciones"),
        # De dónde salió la topografía de esta consulta: 'dtm_kaguya'
        # (experimento A) o 'lola_gds' (vía clásica/respaldo). Con DTM,
        # 'n_puntos_lola' cuenta PÍXELES de la malla, no puntos del láser.
        "via_topografia": topo.get("via"),
    }
    # Se quitan las claves que no tenían dato, para que el resumen sea limpio.
    return {k: v for k, v in resumen.items() if v is not None}


def obtener_datos_sitio(cuerpo: str = "luna",
                        lat: float = -89.9,
                        lon: float = 0.05,
                        radio: float = 0.05,
                        usar_gds: bool = True,
                        usar_dtm: bool = True,
                        con_teselas: bool = False,
                        incluir_tierra: bool = False,
                        resolucion_topografia: str = "30m",
                        aviso=None) -> dict[str, Any]:
    """Devuelve el diccionario completo de parámetros para UN sitio.

    Parámetros:
      cuerpo         'luna' | 'marte' | 'tierra'
      lat, lon       centro del sitio en grados
      radio          semiancho de la caja de búsqueda, en grados. Se recorta
                     a constantes.RADIO_MAX_GRADOS si lo supera (el GDS de
                     PDS tarda desproporcionadamente más con cajas grandes)
      usar_gds       False = salta las consultas GDS (lentas, minutos) y
                     deja solo capas/catálogos; útil para pruebas rápidas
      usar_dtm       True = en la Luna, la topografía sale del DTM de Kaguya
                     (GeoTIFF, segundos) cuando el tile cubre bien la caja
                     (experimento A); si no cubre o falla, cae SOLO ENTONCES
                     a la vía GDS LOLA (el respaldo clásico). Con
                     usar_dtm=False se usa siempre la vía LOLA.
      con_teselas    True = añade URLs WMTS listas para Leaflet/MapLibre
                     (2 llamadas HTTP extra por capa visual)
      incluir_tierra True = añade la sección de análogos terrestres (CMR/GIBS)
      aviso          función opcional (p.ej. print) para informar del avance
                     etapa por etapa; las etapas GDS tardan VARIOS MINUTOS

    Uso típico:
      from colector_datos import obtener_datos_sitio
      datos = obtener_datos_sitio("luna", -89.9, 0.05, 0.05)
    """
    cuerpo = utilidades.normalizar_cuerpo(cuerpo)

    # Tope de caja: ver comentario de RADIO_MAX_GRADOS en constantes.py.
    radio_original = radio
    radio = min(radio, constantes.RADIO_MAX_GRADOS)

    resultado: dict[str, Any] = {
        "metadatos": {
            "cuerpo": cuerpo,
            "lat": lat,
            "lon": lon,
            "radio_grados": radio,
            "consulta": datetime.now().isoformat(timespec="seconds"),
            "fuentes": [],
        },
        "topografia": {},
        "termico": {},
        "superficie": {},
        "iluminacion": {},
    }
    if radio != radio_original:
        resultado["metadatos"]["nota_radio"] = (
            f"radio recortado de ±{radio_original}° a ±{radio}°: cajas más "
            "grandes pueden tardar HORAS en el GDS de PDS; divide en "
            "sub-cajas para más detalle")

    cajas_g = utilidades.cajas_gds(lat, lon, radio)   # (minlat, maxlat, o, e)
    bbox_s = utilidades.caja_stac(lat, lon, radio)    # (o, s, e, n)
    projtype = "polar" if abs(lat) >= 80 else "eq"

    # ------------------------------------------------------------------
    # 1) Catálogo de capas Treks: UNA llamada, se reutiliza en todos los
    #    módulos (topografía, minerales, polvo, iluminación, PSR).
    #    (Solo Luna/Marte: la Tierra no tiene catálogo Treks.)
    # ------------------------------------------------------------------
    capas_trek: list[dict[str, Any]] = []

    # ------------------------------------------------------------------
    # LUNA con GDS: se lanzan EN PARALELO las 4 llamadas independientes
    # (catálogo Treks, GDS Diviner, GDS LOLA y catálogo STAC). Antes iban
    # en serie y la consulta completa esperaba ~77 s: en paralelo tarda lo
    # que la más lenta (~45 s, medido). Con la caché activa las GDS vuelven
    # en milisegundos y el techo lo pone el catálogo Treks (~8 s).
    # ------------------------------------------------------------------
    futuros: dict[str, Any] = {}
    if cuerpo == "moon" and (usar_gds or usar_dtm):
        # El pool corre si hay GDS (Diviner/LOLA) O si hay DTM: la
        # topografía Kaguya NO debe quedar anclada a usar_gds — el
        # docstring promete usar_gds=False + usar_dtm=True como la vía
        # "rápida" (DTM en segundos, sin tocar el GDS lento).
        from concurrent.futures import ThreadPoolExecutor

        tareas = ("catálogo Treks + GDS Diviner + catálogo STAC"
                  if usar_gds else "catálogo Treks + catálogo STAC")
        tareas += " + DTM Kaguya" if usar_dtm else " + GDS LOLA"
        _aviso(aviso, f"En paralelo: {tareas}... "
               "(1ª vez: minutos; con caché: segs)")
        pool = ThreadPoolExecutor(4)
        futuros = {
            "_pool": pool,
            "capas": pool.submit(_capas_trek, cuerpo, projtype),
            "dtm_stac": pool.submit(_dtm_de_stac, cuerpo, bbox_s, lat),
        }
        if usar_gds:
            futuros["diviner"] = pool.submit(termico.datos_diviner, cajas_g)
        if usar_dtm:
            # Experimento A integrado: el análisis DTM se ENCADENA al futuro
            # del STAC (arranca cuando la búsqueda termina y reutiliza sus
            # items, sin repetir la llamada). El GDS LOLA NO se lanza: solo
            # se consultará como fallback si el DTM no cubre la caja.
            futuros["dtm"] = pool.submit(
                _dtm_encadenado, cuerpo, lat, lon, radio,
                futuros["dtm_stac"], aviso)
        elif usar_gds:
            futuros["lola"] = pool.submit(topografia.elevacion_lola, cajas_g)
    elif cuerpo not in ("earth", "mars"):
        # Otros cuerpos (ninguno por ahora): el catálogo se baja en serie.
        capas_trek, fuente_trek = _capas_trek(cuerpo, projtype)
        resultado["metadatos"]["fuentes"].append(fuente_trek)

    # ==================================================================
    # LUNA: datos crudos de LOLA + Diviner (las 2 únicas descargas reales)
    # ==================================================================
    if cuerpo == "moon":
        res_div: dict[str, Any] = {}
        res_lola: dict[str, Any] = {}
        res_dtm: dict[str, Any] = {}
        dtm_precargado: Any = None

        if futuros:
            # Recogemos los resultados del pool paralelo. Las funciones
            # internas ya capturan sus propios errores y devuelven dicts de
            # error, así que .result() no debe lanzar nada inesperado.
            res_div = (futuros["diviner"].result()
                       if "diviner" in futuros else {})
            capas_trek, fuente_trek = futuros["capas"].result()
            resultado["metadatos"]["fuentes"].append(fuente_trek)
            dtm_precargado, fuente_stac = futuros["dtm_stac"].result()
            resultado["metadatos"]["fuentes"].append(fuente_stac)
            if usar_dtm:
                res_dtm = futuros["dtm"].result()
            else:
                res_lola = futuros["lola"].result()
            # OJO: el pool NO se cierra aquí; si el DTM no sirviera, la
            # consulta GDS LOLA de respaldo se lanza sobre este mismo pool.
        elif usar_gds:
            # Ruta de respaldo (no debería usarse: el pool se crea siempre
            # que hay GDS lunar, pero queda por robustez).
            _aviso(aviso, "GDS Diviner (temperaturas): VARIOS MINUTOS...")
            res_div = termico.datos_diviner(cajas_g)
            _aviso(aviso, "GDS LOLA (elevación): otros VARIOS MINUTOS...")
            res_lola = topografia.elevacion_lola(cajas_g)

        # --- sección térmica ------------------------------------------
        term = {k: v for k, v in res_div.items() if not k.startswith("_")}
        if not term:
            term = {"nota": "usar_gds=False o GDS sin datos: descarga el CSV "
                            "de Diviner o usa las capas THEMIS de Treks"}
        resultado["termico"] = term

        # --- sección topográfica --------------------------------------
        # ¿El DTM sirve para ESTA caja? Exige: sin error, >=50% de píxeles
        # válidos ('confiable', lo calcula analizar_sitio) y >=90% de la
        # caja dentro del tile. En los polos NO lo pasa (huecos de sombra:
        # Malapert medido = 2% de píxeles útiles) y cae al LOLA de siempre.
        dtm_util = (usar_dtm and bool(res_dtm)
                    and "error" not in res_dtm
                    and res_dtm.get("confiable", False)
                    and res_dtm.get("cobertura_fraccion", 0.0) >= 0.9)

        if dtm_util:
            # VÍA DTM (experimento A integrado): métricas sobre la malla de
            # Kaguya, en el MISMO formato que la vía LOLA (ver
            # topografia_dtm._a_estadisticas). El GDS LOLA ni se consulta.
            topo: dict[str, Any] = {
                "fuente": "DTM Kaguya TC (USGS STAC) vía rasterio",
                "via": "dtm_kaguya",
                "elevacion_m": res_dtm["elevacion"],
                "pendiente": res_dtm["pendiente"],
                "rugosidad": res_dtm["rugosidad"],
                "metodo_pendiente_rugosidad": (
                    "gradiente sobre la malla del DTM "
                    f"(~{res_dtm.get('resolucion_m')} m/píxel); rugosidad = "
                    "desviación típica dentro de celdas de ~100 m"),
                "crateres_formaciones": res_dtm.get("crateres") or {},
                "dtm_detalle": {
                    "tile": res_dtm.get("tile"),
                    "resolucion_m": res_dtm.get("resolucion_m"),
                    "cobertura_fraccion": res_dtm.get("cobertura_fraccion"),
                    "pixeles_validos_fraccion": res_dtm.get(
                        "pixeles_validos_fraccion"),
                    "tile_en_cache": res_dtm.get("de_cache"),
                    "tiempos_s": {
                        k: res_dtm.get(k) for k in
                        ("stac_s", "descarga_s", "computo_s", "total_s")},
                },
            }
            topo["crateres_formaciones"]["referencias"] = [
                {"mapa_geologico_usgs": constantes.URL_MAPA_GEOLOGICO_LUNA},
            ]
            resultado["metadatos"]["fuentes"].append(
                "DTM Kaguya (rasterio) — topografía sin tocar el GDS LOLA")
        else:
            # VÍA LOLA (GDS): la clásica, y respaldo del DTM. Con
            # usar_dtm=True esta consulta SOLO se lanza ahora (cuando ya se
            # sabe que el DTM no sirve); si el DTM sirve, el GDS LOLA ni se
            # molesta (menos carga en el servidor frágil de PDS).
            if usar_dtm and res_dtm:
                motivo = res_dtm.get("error") or (
                    f"cobertura {res_dtm.get('cobertura_fraccion')} · "
                    "píxeles válidos "
                    f"{res_dtm.get('pixeles_validos_fraccion')}")
                _aviso(aviso, f"DTM no usable en este sitio ({motivo}): "
                       "fallback a GDS LOLA (VARIOS MINUTOS)...")
                resultado["metadatos"]["fuentes"].append(
                    f"DTM Kaguya DESCARTADO ({motivo})")
            if futuros and usar_gds:
                if usar_dtm:
                    res_lola = futuros["_pool"].submit(
                        topografia.elevacion_lola, cajas_g).result()
                else:
                    res_lola = futuros["lola"].result()
            elif usar_gds:
                _aviso(aviso, "GDS LOLA (elevación): VARIOS MINUTOS...")
                res_lola = topografia.elevacion_lola(cajas_g)

            topo = {"fuente": "LOLA (GDS) + DTM Kaguya (USGS STAC) + Treks",
                    "via": "lola_gds"}
            if res_lola.get("elevacion_m"):
                topo["elevacion_m"] = res_lola["elevacion_m"]
                geom = utilidades.pendiente_y_rugosidad(
                    res_lola["puntos"], constantes.RADIO_DATUM_LUNA_M)
                topo["pendiente"] = geom.get("pendiente_grados")
                topo["rugosidad"] = geom.get("rugosidad_m")
                topo["metodo_pendiente_rugosidad"] = geom.get("metodo")
                topo["crateres_formaciones"] = utilidades.detectar_crateres(
                    res_lola["puntos"], constantes.RADIO_DATUM_LUNA_M)
                topo["crateres_formaciones"]["referencias"] = [
                    {"mapa_geologico_usgs": constantes.URL_MAPA_GEOLOGICO_LUNA},
                ]
            else:
                topo["elevacion_m"] = res_lola.get(
                    "error", "sin datos (usar_gds=False?)")

        # El catálogo STAC ya está en mano (paralelo) o se pide ahora.
        if futuros:
            topo["dtm_descargables"] = dtm_precargado
        else:
            try:
                _aviso(aviso, "Catálogo STAC de DTM (USGS)...")
                topo["dtm_descargables"] = topografia.dtm_disponibles(
                    cuerpo, bbox_s, lat)
                resultado["metadatos"]["fuentes"].append("USGS STAC (DTM)")
            except Exception as exc:
                topo["dtm_descargables"] = {"error": str(exc)}
        topo["capas_trek"] = topografia.capas_topografia_trek(capas_trek)
        resultado["topografia"] = topo
        if futuros:
            futuros["_pool"].shutdown()

        # --- sección superficie ---------------------------------------
        resultado["superficie"] = superficie.datos_superficie(res_div, capas_trek)
        resultado["metadatos"]["fuentes"].append("PDS Search (Clementine)")

        # --- sección iluminación --------------------------------------
        resultado["iluminacion"] = iluminacion.datos_iluminacion(
            capas_trek, res_div)

    # ==================================================================
    # MARTE: no hay LOLA ni Diviner (instrumentos lunares), pero la
    # topografía sale del DTM de CTX/HiRISE del STAC (la misma receta del
    # experimento A lunar: tile GeoTIFF de S3 estático, window read). El
    # resto de parámetros salen de las capas de Mars Trek. TODO con el
    # MISMO formato de diccionario que la Luna, para comparar cuerpos.
    # ==================================================================
    elif cuerpo == "mars":
        from concurrent.futures import ThreadPoolExecutor

        _aviso(aviso, "En paralelo: catálogo Treks + catálogo STAC + "
               "análisis DTM (CTX/HiRISE)... (1ª vez: minutos; con caché: segs)")
        pool = ThreadPoolExecutor(3)
        futuros_m = {
            "capas": pool.submit(_capas_trek, cuerpo, projtype),
            "dtm_stac": pool.submit(_dtm_de_stac, cuerpo, bbox_s, lat),
        }
        # El análisis DTM se ENCADENA al futuro del STAC (reutiliza sus
        # items, sin repetir la llamada) — el mismo patrón de la Luna.
        futuros_m["dtm"] = pool.submit(
            _dtm_encadenado, cuerpo, lat, lon, radio,
            futuros_m["dtm_stac"], aviso)
        capas_trek, fuente_trek = futuros_m["capas"].result()
        resultado["metadatos"]["fuentes"].append(fuente_trek)
        dtm_precargado, fuente_stac = futuros_m["dtm_stac"].result()
        resultado["metadatos"]["fuentes"].append(fuente_stac)
        res_dtm = futuros_m["dtm"].result()
        pool.shutdown()

        pc = constantes.PALABRAS_CLAVE_CAPAS

        # ¿El DTM marciano sirve? Política RELAJADA respecto a la Luna
        # (cobertura >= 0.5): en Marte NO existe LOLA/GDS de respaldo, así
        # que un tile que cubra la mitad de la caja sigue siendo LA única
        # elevación puntual disponible. La cobertura queda anotada.
        dtm_util = (usar_dtm and bool(res_dtm)
                    and "error" not in res_dtm
                    and res_dtm.get("confiable", False)
                    and res_dtm.get("cobertura_fraccion", 0.0) >= 0.5)

        if dtm_util:
            topo: dict[str, Any] = {
                "fuente": "DTM MRO CTX/HiRISE (USGS STAC) vía rasterio",
                "via": "dtm_mro",
                "elevacion_m": res_dtm["elevacion"],
                "pendiente": res_dtm["pendiente"],
                "rugosidad": res_dtm["rugosidad"],
                "metodo_pendiente_rugosidad": (
                    "gradiente sobre la malla del DTM "
                    f"(~{res_dtm.get('resolucion_m')} m/píxel); rugosidad = "
                    "desviación típica dentro de celdas de ~100 m (MISMA "
                    "definición que la vía lunar, para comparar cuerpos)"),
                "crateres_formaciones": res_dtm.get("crateres") or {},
                "dtm_detalle": {
                    "tile": res_dtm.get("tile"),
                    "resolucion_m": res_dtm.get("resolucion_m"),
                    "cobertura_fraccion": res_dtm.get("cobertura_fraccion"),
                    "pixeles_validos_fraccion": res_dtm.get(
                        "pixeles_validos_fraccion"),
                    "tile_en_cache": res_dtm.get("de_cache"),
                    "tiempos_s": {
                        k: res_dtm.get(k) for k in
                        ("stac_s", "descarga_s", "computo_s", "total_s")},
                },
            }
            if topo["dtm_detalle"]["cobertura_fraccion"] < 0.9:
                topo["nota_cobertura"] = (
                    "el tile cubre el "
                    f"{topo['dtm_detalle']['cobertura_fraccion'] * 100:.0f} % "
                    "de la caja: las métricas describen esa fracción "
                    "(no hay DTM más ancho disponible en el STAC)")
            topo["crateres_formaciones"]["referencias"] = [
                {"mapa_geologico_usgs": constantes.URL_MAPA_GEOLOGICO_MARTE},
            ]
            resultado["metadatos"]["fuentes"].append(
                "DTM MRO CTX/HiRISE (rasterio) — elevación sin PDS ODE")
        else:
            # Sin DTM utilizable (Gale p.ej. no tiene tiles controlados):
            # la sección queda en catálogos, con nota HONESTA de por qué.
            if usar_dtm and res_dtm:
                resultado["metadatos"]["fuentes"].append(
                    f"DTM MRO DESCARTADO ({res_dtm.get('error')})")
            topo = {
                "fuente": "DTM HiRISE/CTX (USGS STAC) + capas Mars Trek",
                "via": "catalogos",
                "nota_elevacion": (
                    "En este sitio no hay tile DEM (CTX/HiRISE controlado) "
                    "que cubra la caja y no existe LOLA: la elevación "
                    "puntual exige descargar un DTM de PDS ODE o leer las "
                    "teselas DEM de Mars Trek (ver dtm_descargables)."),
            }
        topo["dtm_descargables"] = dtm_precargado
        topo["capas_trek"] = topografia.capas_topografia_trek(capas_trek)
        resultado["topografia"] = topo

        resultado["termico"] = {
            "fuente": "THEMIS (Mars Trek) / TES",
            "nota": ("No hay servicio tipo GDS para temperatura puntual en "
                     "Marte: la LST se obtiene de THEMIS (capas abajo) o "
                     "descargando products de MGS-TES/MRO-THEMIS en PDS ODE."),
            "capas_trek": utilidades.capas_por_keyword(capas_trek,
                                                       pc["temperatura"]),
        }
        resultado["superficie"] = superficie.datos_superficie(
            None, capas_trek, cuerpo="mars")
        resultado["iluminacion"] = iluminacion.datos_iluminacion(
            capas_trek, None, cuerpo="mars")

    # ==================================================================
    # TIERRA: con la misma envoltura (metadatos + registro) y AHORA con
    # datos crudos en el MISMO formato que la Luna/Marte (rama
    # `tierra-datos-crudos`): topografía GLO-30, térmico POWER,
    # superficie Sentinel-2, iluminación local. Se lanza en paralelo un
    # pool de 3 (topografía | térmico | superficie); la iluminación es
    # local (0 llamadas) y `analogos_tierra` conserva el catálogo CMR/
    # GIBS como punteros opcionales.
    # ==================================================================
    else:  # earth
        from concurrent.futures import ThreadPoolExecutor

        _aviso(aviso, f"En paralelo: DEM GLO-{resolucion_topografia[:-1]} + "
               "POWER (térmico) + Sentinel-2 (superficie)... (tibio: segundos)")
        pool = ThreadPoolExecutor(3)
        futuros_t = {
            "topo": pool.submit(topografia_tierra.analizar_sitio,
                                lat, lon, radio, "descargar", None,
                                resolucion_topografia),
            "term": pool.submit(termico_tierra.datos_termico_tierra,
                                lat, lon),
            "sup": pool.submit(superficie_tierra.datos_superficie_tierra,
                               lat, lon, radio),
        }
        res_topo = futuros_t["topo"].result()
        res_term = futuros_t["term"].result()
        res_sup = futuros_t["sup"].result()
        pool.shutdown()

        # --- topografía: misma estructura que la vía DTM lunar/marciana ---
        if "error" in res_topo:
            resultado["topografia"] = {
                "fuente": res_topo.get("fuente", "Copernicus GLO-30"),
                "via": "catalogos",
                "error": res_topo["error"],
                "nota_elevacion": (
                    "no se pudo leer el tile GLO-30 (¿sitio en mar abierto "
                    "o red?): los catálogos CMR de abajo indican qué "
                    "colecciones cubren la caja"),
            }
        else:
            topo: dict[str, Any] = {
                "fuente": "Copernicus DEM GLO-30 (AWS público) vía rasterio",
                # 'via' refleja la resolución pedida: 'glo30' (default,
                # ~30 m/px) o 'glo90' (criba rápida, ~90 m/px). Así el
                # resumen del registro es trazable entre corridas.
                "via": ("glo90" if res_topo.get("resolucion") == "90m"
                        else "glo30"),
                "elevacion_m": res_topo["elevacion"],
                "pendiente": res_topo["pendiente"],
                "rugosidad": res_topo["rugosidad"],
                "metodo_pendiente_rugosidad": (
                    "gradiente sobre la malla del DEM "
                    f"(~{res_topo.get('resolucion_m')} m/píxel); rugosidad = "
                    "desviación típica dentro de celdas de ~100 m (MISMA "
                    "definición que la vía lunar/marciana)"),
                "crateres_formaciones": res_topo.get("crateres") or {},
                "dtm_detalle": {
                    "tile": res_topo.get("tile"),
                    "resolucion_m": res_topo.get("resolucion_m"),
                    "datum_elevacion": res_topo.get("datum_elevacion"),
                    "cobertura_fraccion": res_topo.get("cobertura_fraccion"),
                    "pixeles_validos_fraccion": res_topo.get(
                        "pixeles_validos_fraccion"),
                    "tile_en_cache": res_topo.get("de_cache"),
                    "tiempos_s": {k: res_topo.get(k) for k in
                                  ("stac_s", "descarga_s", "computo_s",
                                   "total_s")},
                },
            }
            if res_topo.get("nota_oceano"):
                topo["nota_oceano"] = res_topo["nota_oceano"]
            resultado["topografia"] = topo

        # --- térmico / superficie / iluminación: los módulos ya devuelven
        #     las claves estándar, van casi tal cual ------------------------
        resultado["termico"] = {k: v for k, v in res_term.items()
                                if not k.startswith("_")}
        resultado["superficie"] = res_sup
        resultado["iluminacion"] = iluminacion_tierra.datos_iluminacion_tierra(
            lat, lon)

        resultado["metadatos"]["fuentes"].extend([
            "Copernicus GLO-30 (topografía)",
            "NASA POWER (térmico)",
            "Sentinel-2 Earth Search (superficie)",
            "geometría solar local (iluminación)",
        ])
        # Catálogo CMR/GIBS opcional (punteros + teselas para el visor):
        # no es dato crudo, es el "dónde pedir más".
        if incluir_tierra:
            _aviso(aviso, "Análogos Tierra (catálogo CMR + GIBS)...")
            resultado["analogos_tierra"] = analogos_tierra.datos_tierra(
                lat, lon, max(radio, 0.5))
        resultado["metadatos"]["fuentes"].append(
            "CMR/GIBS/Copernicus (análogos Tierra)")
        try:
            ruta_registro = guardar_en_registro(resultado)
            resultado["metadatos"]["registro"] = str(ruta_registro)
        except Exception as exc:
            resultado["metadatos"]["registro"] = f"no se pudo guardar: {exc}"
        return resultado

    # ------------------------------------------------------------------
    # Opcionales: URLs de teselas para el visor y análogos terrestres
    # ------------------------------------------------------------------
    if con_teselas:
        pc = constantes.PALABRAS_CLAVE_CAPAS
        resultado["teselas_para_mapa"] = utilidades.urls_de_tesela(
            cuerpo, capas_trek,
            {"dem": pc["dem"],
             "pendiente": pc["pendiente"],
             "rugosidad": pc["rugosidad"],
             "iluminacion": pc["iluminacion"],
             "psr": pc["sombra"]})

    if incluir_tierra:
        resultado["analogos_tierra"] = analogos_tierra.datos_tierra(
            lat, lon, max(radio, 0.5))

    # ------------------------------------------------------------------
    # Registro: TODA consulta queda guardada en data/registro_sitios.json
    # (si el sitio ya estaba, se actualiza su entrada con la nueva fecha).
    # ------------------------------------------------------------------
    try:
        ruta_registro = guardar_en_registro(resultado)
        resultado["metadatos"]["registro"] = str(ruta_registro)
    except Exception as exc:
        # El registro es un extra: si no se puede escribir, la consulta
        # sigue siendo válida y solo anotamos el porqué.
        resultado["metadatos"]["registro"] = f"no se pudo guardar: {exc}"

    return resultado
