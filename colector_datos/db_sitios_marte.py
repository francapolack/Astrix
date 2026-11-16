"""db_sitios_marte.py — DB LOCAL de sitios marcianos con nombre (NSAC).

PROBLEMA QUE RESUELVE: en Marte el usuario no sabe qué lugares tienen
datos de verdad. Adivinar coordenadas da muchas cajas sin tile DTM y sin
observaciones. Esta DB convierte "¿dónde hay datos?" en una lista
consultable: indexa los ~2.100 lugares CON NOMBRE del Gazetteer de la
IAU/USGS y, para cada uno, guarda:

  1) Topografía en el MISMO formato de comparación del proyecto
     (elevacion_media_m, pendiente_media_grados, rugosidad_media_m,
     via_topografia='dtm_mro'), calculada SIN descargar tiles: se lee el
     trozo del GeoTIFF del STAC por HTTP (/vsicurl, verificado en Jezero:
     mismos números que el tile bajado en ~6 s).
  2) Disponibilidad de mediciones múltiples (THEMIS IRBTR4 vía ODE), pero
     SOLO como metadatos de una ventana corta: el total de observaciones
     que hay en la caja y el detalle (id, fecha, hora solar) de las de un
     mes como máximo hacia atrás desde la última. Nunca se inventan
     valores térmicos: THEMIS IRBTR es temperatura de brillo, y calcular
     de verdad la capa térmica es trabajo de `api.py`, no de esta DB.

Fuentes (sondeadas y verificadas, ver NOTAS_NOCTURNAS.md):
  - Gazetteer: UNA página HTML con TODOS los lugares de Marte
    (planetarynames.wr.usgs.gov/SearchResults?Target=20_Mars&PageSize=500,
    ~3 MB, ~3 s); la tabla 'search_results' se parsea con regex porque el
    'CSV' del sitio se genera con JavaScript en el navegador.
  - STAC: búsqueda por bbox (pequeña, cacheada por cache_catalogo); NUNCA
    se pagina la colección entera (44.628 items, el servidor da 502).
  - ODE: ODY/THEMIS/IRBTR4 (PDS4, con Observation_time; el 'Count' que
    devuelve ODE replica el límite pedido, no el total real).

Esquema: sitios (uno por lugar: stats + trazabilidad del tile + THEMIS)
y mediciones (observaciones de la ventana, clave (sitio_id, producto_id)).

La DB es RESUMIBLE: indexar puede repetirse (INSERT OR IGNORE) y
enriquecer solo procesa sitios 'pendiente'; los fallos quedan como
'sin_dtm' (no hay tile que cubra la caja) o 'error' (otra causa) y se
pueden reintentar con el comando 'reintentar'.

CLI:
  python -m colector_datos.db_sitios_marte indexar
  python -m colector_datos.db_sitios_marte enriquecer --max 120 --hilos 2
  python -m colector_datos.db_sitios_marte listar --n 15
  python -m colector_datos.db_sitios_marte reintentar [--todo]
  python -m colector_datos.db_sitios_marte estado
"""

from __future__ import annotations

import html as _html
import json
import re
import sqlite3
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from . import constantes, topografia, topografia_dtm, utilidades

# Ruta de la DB: data/ está fuera de git (igual que las cachés y el
# registro): es datos derivados, no código.
RUTA_DB = Path(constantes.RUTA_REGISTRO).parent / "db" / "sitios_marte.db"

# Gazetteer: UNA página trae TODOS los lugares con nombre de Marte
# (2.100 filas; PageSize=500 es el máximo y ya pagina el HTML entero).
URL_GAZETTEER = ("https://planetarynames.wr.usgs.gov/SearchResults"
                 "?Target=20_Mars&PageSize=500")

# Qué lugares entran en la DB:
# - 'Albedo Feature' FUERA: son manchas de albedo sin relieve físico, no
#   describen la superficie (127 de las 2.100 filas).
# - Cráteres SOLO si son grandes (>= 40 km): hay 1.250 con nombre y
#   enriquecer cada uno cuesta una lectura remota; con 40 km quedan los
#   estructuralmente interesantes (cuenca, borde bien resuelto por el
#   DTM de ~20 m/px) y una lista manejable.
TIPOS_EXCLUIDOS = {"Albedo Feature"}
DIAMETRO_CRATER_MIN_KM = 40.0

# Radio de la caja para los cráteres: la mitad del diámetro convertida a
# grados (1° ≈ 111.32 km sobre el meridiano) y corregida por latitud
# (los meridianos se juntan hacia el polo). Se recorta a [0.05, 0.5]°:
# por debajo de 0.05 la caja es más chica que el tile DTM que resuelve;
# 0.5 es RADIO_MAX_GRADOS (techo del proyecto). Los NO cráteres usan 0.2°
# fijo (sus diámetros del Gazetteer son de cuenca completa, p.ej. Hellas
# >2.000 km: una caja así no se puede analizar).
RADIO_DEFAULT_GRADOS = 0.2
RADIO_MIN_GRADOS = 0.05
RADIO_MAX_GRADOS = 0.5
KM_POR_GRADO = 111.32

# Ventana de mediciones múltiples: SOLO las observaciones THEMIS de un
# mes hacia atrás desde la última (requisito del desafío: rangos de
# fecha cortos para los datos con varias mediciones).
VENTANA_DIAS = 31

# Fuente de mediciones múltiples (verificada con el IIPT de ODE: es la
# combinación válida con fechas de observación y datos PDS4).
THEMIS_IHID, THEMIS_IID, THEMIS_PT = "ODY", "THEMIS", "IRBTR4"
THEMIS_TIPO = "THEMIS_IRBTR4"

# Lock global: SQLite no comparte conexiones entre hilos, así que cada
# escritura abre la suya; el lock serializa las transacciones para no
# pisarse con 'database is locked' en Windows.
_LOCK_SQLITE = threading.Lock()


# ---------------------------------------------------------------------------
# 1. Conexión y esquema
# ---------------------------------------------------------------------------

def _conectar() -> sqlite3.Connection:
    """Abre la DB (creando carpeta y tablas si faltan)."""
    RUTA_DB.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(RUTA_DB, timeout=60)
    con.row_factory = sqlite3.Row
    con.execute("""
        CREATE TABLE IF NOT EXISTS sitios (
            sitio_id     TEXT PRIMARY KEY,   -- 'mars@lat,lon±radio'
            nombre       TEXT NOT NULL,
            tipo         TEXT,
            diametro_km  REAL,
            lat          REAL NOT NULL,
            lon          REAL NOT NULL,
            radio        REAL NOT NULL,
            estado       TEXT DEFAULT 'pendiente',  -- pendiente|listo|sin_dtm|error
            error        TEXT,
            -- topografía (formato de comparación del proyecto)
            elevacion_min_m    REAL,
            elevacion_media_m  REAL,
            elevacion_max_m    REAL,
            elevacion_mediana_m REAL,
            pendiente_media_grados REAL,
            rugosidad_media_m  REAL,
            n_pixeles          INTEGER,
            cobertura          REAL,
            resolucion_m       REAL,
            n_crateres         INTEGER,
            nota               TEXT,
            -- trazabilidad del tile DTM usado
            tile_id      TEXT,
            tile_url     TEXT,
            fuente_dtm   TEXT,
            -- THEMIS: metadatos de disponibilidad (no valores inventados)
            themis_n_obs      INTEGER,
            themis_n_ventana  INTEGER,
            themis_ventana_ini TEXT,
            themis_ventana_fin TEXT,
            actualizado  TEXT
        )
    """)
    con.execute("""
        CREATE TABLE IF NOT EXISTS mediciones (
            sitio_id    TEXT NOT NULL,
            producto_id TEXT NOT NULL,
            tipo        TEXT DEFAULT 'THEMIS_IRBTR4',
            fecha_obs   TEXT,
            solar_time  TEXT,
            PRIMARY KEY (sitio_id, producto_id)
        )
    """)
    con.commit()
    return con


# ---------------------------------------------------------------------------
# 2. Indexación del Gazetteer (lugares con nombre -> filas 'pendiente')
# ---------------------------------------------------------------------------

def _numero(texto: Any) -> float | None:
    """Texto del Gazetteer -> float (o None si está vacío/raro)."""
    if texto is None:
        return None
    s = str(texto).strip().replace(",", "")
    if not s or not re.fullmatch(r"-?\d+(\.\d+)?", s):
        return None
    return float(s)


def _radio_de(diam_km: float | None, lat: float, es_crater: bool) -> float:
    """Semiancho de la caja en grados para un lugar del Gazetteer.

    Cráteres: mitad del diámetro en grados, corregido por latitud
    (arcos de meridiano: 1° = pi·R/180 ≈ 111.32 km; el cos(lat) corrige
    el acortamiento horizontal hacia los polos). Recortado a [0.05, 0.5].
    Resto de tipos: 0.2° fijo (ver constantes de arriba).
    """
    if not es_crater or not diam_km or diam_km <= 0:
        return RADIO_DEFAULT_GRADOS
    radio = (diam_km / 2.0) / KM_POR_GRADO / max(
        0.01, _math_cos(lat))
    return min(RADIO_MAX_GRADOS, max(RADIO_MIN_GRADOS, radio))


def _math_cos(grados: float) -> float:
    import math
    return math.cos(math.radians(grados))


def _filas_gazetteer(pagina_html: str) -> list[list[str]]:
    """Parsea la tabla 'search_results' del HTML del Gazetteer.

    La página es HTML 4 normal: la tabla de resultados tiene class
    'search_results' (el 'CSV' del sitio se genera en el navegador con
    JS a partir de esa tabla, por eso NO existe un endpoint CSV real).
    Cada fila de datos empieza con el Feature ID (un número).
    """
    i = pagina_html.find("search_results")
    if i < 0:
        return []
    filas = re.findall(r"<tr[^>]*>(.*?)</tr>", pagina_html[i:], re.S)
    out = []
    for fila in filas:
        celdas = re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", fila, re.S)
        limpias = [
            _html.unescape(re.sub(r"\s+", " ",
                                  re.sub(r"<[^>]+>", "", c)).strip())
            for c in celdas
        ]
        # Fila de datos = la primera celda es el Feature ID (dígitos).
        if limpias and limpias[0].isdigit():
            out.append(limpias)
    return out


def indexar_gazetteer(aviso=None) -> dict[str, Any]:
    """Descarga la página del Gazetteer y llena 'sitios' con 'pendiente'.

    Columnas de la tabla (verificadas contra filas reales):
      [0] Feature ID | [1] nombre | [4] diámetro km | [5] lat centro |
      [6] lon centro (convenio 0-360 Este) | [14] tipo de formación.

    Idempotente: 'INSERT OR IGNORE' — repetir el comando no resetea los
    sitios ya enriquecidos y solo añade los nuevos.
    """
    def _aviso(msg: str) -> None:
        if aviso:
            aviso(msg)

    from nsac.http import get

    _aviso(f"descargando Gazetteer ({URL_GAZETTEER})...")
    t0 = time.perf_counter()
    r = get(URL_GAZETTEER, timeout=120)
    filas = _filas_gazetteer(r.text)
    _aviso(f"{len(filas)} lugares parseados en "
           f"{round(time.perf_counter() - t0, 1)} s")

    con = _conectar()
    insertados, filtrados_crateres, excluidos = 0, 0, 0
    with _LOCK_SQLITE:
        for f in filas:
            if len(f) <= 14:
                continue  # fila recortada: fuera
            tipo = f[14]
            if tipo in TIPOS_EXCLUIDOS:
                excluidos += 1
                continue
            nombre = f[1]
            diam = _numero(f[4])
            lat = _numero(f[5])
            lon360 = _numero(f[6])
            if lat is None or lon360 is None:
                continue  # sin coordenadas: no se puede consultar nada
            es_crater = tipo.startswith("Crater")
            if es_crater and (diam is None or diam < DIAMETRO_CRATER_MIN_KM):
                filtrados_crateres += 1
                continue
            # Gazetteer usa 0-360 Este; el proyecto usa -180..180.
            lon = lon360 if lon360 <= 180.0 else lon360 - 360.0
            radio = _radio_de(diam, lat, es_crater)
            sitio_id = f"mars@{lat:.2f},{lon:.2f}±{radio:.2f}"
            con.execute(
                """INSERT OR IGNORE INTO sitios
                   (sitio_id, nombre, tipo, diametro_km, lat, lon, radio,
                    estado, actualizado)
                   VALUES (?, ?, ?, ?, ?, ?, ?, 'pendiente', ?)""",
                (sitio_id, nombre, tipo, diam, lat, lon, radio,
                 datetime.now().isoformat(timespec="seconds")))
            insertados += 1
        con.commit()

    total = con.execute(
        "SELECT COUNT(*) FROM sitios").fetchone()[0]
    con.close()
    resumen = {
        "filas_gazetteer": len(filas),
        "nuevos_insertados": insertados,
        "crateres_filtrados_por_diametro": filtrados_crateres,
        "excluidos_albedo": excluidos,
        "total_en_db": total,
        "db": str(RUTA_DB),
    }
    _aviso("indexado: " + json.dumps(resumen, ensure_ascii=False))
    return resumen


# ---------------------------------------------------------------------------
# 3. Enriquecimiento (stats topográficos + THEMIS por sitio)
# ---------------------------------------------------------------------------

def _themis_de_sitio(lat: float, lon: float, radio: float,
                     limite: int = 500) -> dict[str, Any]:
    """Observaciones THEMIS IRBTR4 de la caja vía ODE + ventana de un mes.

    Devuelve metadatos de disponibilidad: total de observaciones en la
    caja, cuántas caen en la ventana [última fecha − 31 días, última
    fecha] y la lista de productos DE LA VENTANA (id, fecha, hora solar)
    para guardar en 'mediciones'. NO devuelve ni calcula temperaturas.

    ODE quiere longitudes 0-360 (convenio GDS): `utilidades.cajas_gds`
    las convierte y parte la caja si cruza el meridiano 0/360.
    """
    from nsac.sources import pds

    productos: dict[str, dict[str, Any]] = {}
    for (lat_sur, lat_norte, oeste, este) in utilidades.cajas_gds(
            lat, lon, radio):
        res = pds.ode_products(
            THEMIS_IHID, THEMIS_IID, THEMIS_PT, target="mars",
            bbox=(lat_sur, lat_norte, oeste, este), limit=limite)
        for p in res.get("products") or []:
            if p.get("id"):
                productos[p["id"]] = p

    # Fechas de observación (PDS4: Observation_time con 'Z' final).
    fechas: dict[str, datetime] = {}
    for pid, p in productos.items():
        texto = p.get("observation_time") or ""
        try:
            fechas[pid] = datetime.fromisoformat(
                texto.replace("Z", "+00:00"))
        except ValueError:
            continue  # producto sin fecha parseable: se ignora para ventana

    salida: dict[str, Any] = {
        "n_obs": len(productos),
        "n_ventana": 0,
        "ventana_ini": None,
        "ventana_fin": None,
        "productos_ventana": [],
    }
    if not fechas:
        return salida

    fin = max(fechas.values())
    ini = fin - timedelta(days=VENTANA_DIAS)
    en_ventana = [pid for pid, f in fechas.items() if f >= ini]
    salida.update({
        "n_ventana": len(en_ventana),
        "ventana_ini": ini.date().isoformat(),
        "ventana_fin": fin.date().isoformat(),
        "productos_ventana": [
            {
                "producto_id": pid,
                "tipo": THEMIS_TIPO,
                "fecha_obs": productos[pid].get("observation_time"),
                "solar_time": productos[pid].get("solar_time"),
            }
            for pid in sorted(en_ventana)
        ],
    })
    return salida


def _nota_de_cobertura(res: dict[str, Any]) -> str | None:
    """Nota honesta cuando el tile no cubre todo (misma que usa api.py).

    Política de Marte RELAJADA (>=50 %, no hay LOLA de respaldo), pero
    anotada: si el tile cubre <90 % de la caja, las métricas describen
    esa fracción (mismo texto/nota que api.py pone en 'nota_cobertura').
    Además se avisa si hay huecos de píxeles dentro del trozo leído.
    """
    notas = []
    cov = res.get("cobertura_fraccion")
    if isinstance(cov, (int, float)) and cov < 0.9:
        notas.append(f"el tile cubre el {round(cov * 100)}% de la caja: "
                     "las métricas describen esa fracción")
    val = res.get("pixeles_validos_fraccion")
    if isinstance(val, (int, float)) and val < 0.5:
        notas.append(f"solo {round(val * 100)}% de píxeles válidos "
                     "(huecos del DTM)")
    return "; ".join(notas) or None


def _enriquecer_sitio(fila: sqlite3.Row, aviso=None) -> dict[str, Any]:
    """Procesa UN sitio 'pendiente' y devuelve el UPDATE listo para la DB.

    Red por sitio: 1 búsqueda STAC pequeña (cacheada por cache_catalogo)
    + lectura remota del trozo del tile (/vsicurl, ~6 s) + 1-2 consultas
    ODE (~3 s). Nada se descarga completo.
    """
    def _aviso(msg: str) -> None:
        if aviso:
            aviso(msg)

    lat, lon, radio = fila["lat"], fila["lon"], fila["radio"]
    sitio_id = fila["sitio_id"]
    cambios: dict[str, Any] = {"sitio_id": sitio_id,
                               "actualizado": datetime.now().isoformat(
                                   timespec="seconds")}

    try:
        # --- topografía: STAC + análisis remoto ---------------------------
        bbox_stac = utilidades.caja_stac(lat, lon, radio)
        items = topografia.dtm_disponibles("mars", bbox_stac, lat)
        res = topografia_dtm.analizar_sitio(
            lat, lon, radio, items_stac=items, cuerpo="mars",
            modo_tile="remoto")

        sin_tile = "sin tile DEM" in str(res.get("error", ""))
        # MISMA política que api.py para Marte (relajada >= 0.5): un DTM
        # con poca cobertura NO da 'listo' — si entrara en la DB con
        # via_topografia='dtm_mro' significaría otra cosa que en
        # obtener_datos_sitio(). 'confiable' = >=50 % de píxeles válidos.
        cobertura = res.get("cobertura_fraccion") or 0.0
        dtm_util = ("elevacion" in res and res.get("confiable", False)
                    and cobertura >= 0.5)
        if sin_tile or not dtm_util:
            # Sin tile que cubra la caja (Gale: verificado, 0 tiles
            # controlados) o cobertura/píxeles insuficientes: estados
            # distintos para poder distinguir 'no hay datos' de 'falló'.
            cambios["estado"] = "sin_dtm"
            if sin_tile:
                cambios["error"] = str(res.get("error", ""))[:300]
            else:
                cambios["error"] = (
                    f"DTM descartado: cobertura {round(cobertura * 100)}% "
                    f"/ píxeles válidos "
                    f"{round((res.get('pixeles_validos_fraccion') or 0) * 100)}% "
                    f"< política 50% ({str(res.get('error') or '')[:120]})")
            return cambios

        elev = res["elevacion"]
        pend = res.get("pendiente") or {}
        rug = res.get("rugosidad") or {}
        crateres = res.get("crateres") or {}
        cambios.update({
            "estado": "listo",
            "error": None,
            "elevacion_min_m": elev.get("min"),
            "elevacion_media_m": elev.get("media"),
            "elevacion_max_m": elev.get("max"),
            "elevacion_mediana_m": elev.get("mediana"),
            "pendiente_media_grados": pend.get("media"),
            "rugosidad_media_m": rug.get("media") if "media" in rug else None,
            "n_pixeles": elev.get("n_pixeles"),
            "cobertura": res.get("cobertura_fraccion"),
            "resolucion_m": res.get("resolucion_m"),
            "n_crateres": crateres.get("n_candidatos"),
            "nota": _nota_de_cobertura(res),
            "tile_id": res.get("tile"),
            "tile_url": res.get("url"),
            "fuente_dtm": res.get("fuente"),
        })
        _aviso(f"  topografía OK ({res.get('resolucion_m')} m/px, "
               f"cobertura {res.get('cobertura_fraccion')})")

    except Exception as exc:  # red caída, JSON raro, lo que sea
        cambios["estado"] = "error"
        cambios["error"] = str(exc)[:300]
        return cambios

    # --- THEMIS (metadatos de la ventana) ---------------------------------
    try:
        themis = _themis_de_sitio(lat, lon, radio)
        cambios.update({
            "themis_n_obs": themis["n_obs"],
            "themis_n_ventana": themis["n_ventana"],
            "themis_ventana_ini": themis["ventana_ini"],
            "themis_ventana_fin": themis["ventana_fin"],
        })
        cambios["_productos_ventana"] = themis["productos_ventana"]
        _aviso(f"  THEMIS: {themis['n_obs']} obs totales | "
               f"{themis['n_ventana']} en ventana "
               f"{themis['ventana_ini']}..{themis['ventana_fin']}")
    except Exception as exc:
        # THEMIS es un extra: si ODE falla el sitio queda 'listo' igual,
        # con la nota del fallo.
        cambios["nota"] = "; ".join(
            n for n in (cambios.get("nota"),
                        f"THEMIS no disponible ({str(exc)[:120]})") if n)
    return cambios


def _guardar(cambios: dict[str, Any]) -> None:
    """Escribe el resultado de un sitio (UPDATE + mediciones) en la DB."""
    productos = cambios.pop("_productos_ventana", [])
    campos = [
        "estado", "error", "elevacion_min_m", "elevacion_media_m",
        "elevacion_max_m", "elevacion_mediana_m", "pendiente_media_grados",
        "rugosidad_media_m", "n_pixeles", "cobertura", "resolucion_m",
        "n_crateres", "nota", "tile_id", "tile_url", "fuente_dtm",
        "themis_n_obs", "themis_n_ventana", "themis_ventana_ini",
        "themis_ventana_fin", "actualizado",
    ]
    asig = ", ".join(f"{c} = ?" for c in campos)
    valores = [cambios.get(c) for c in campos]
    with _LOCK_SQLITE:
        con = _conectar()
        try:
            con.execute(
                f"UPDATE sitios SET {asig} WHERE sitio_id = ?",
                valores + [cambios["sitio_id"]])
            for p in productos:
                con.execute(
                    """INSERT OR IGNORE INTO mediciones
                       (sitio_id, producto_id, tipo, fecha_obs, solar_time)
                       VALUES (?, ?, ?, ?, ?)""",
                    (cambios["sitio_id"], p["producto_id"], p["tipo"],
                     p["fecha_obs"], p["solar_time"]))
            con.commit()
        finally:
            con.close()


def enriquecer(max_sitios: int = 50, hilos: int = 2,
               aviso=None) -> dict[str, Any]:
    """Calcula topografía + THEMIS para los sitios 'pendiente'.

    Resumible: cada sitio procesado queda 'listo'/'sin_dtm'/'error' en la
    DB; repetir la llamada continúa donde quedó. Paralelismo con hilos
    (la red manda: hilos, no procesos) — 2-3 máximo para no castigar al
    STAC ni a ODE.

    Devuelve contadores para el log de la sesión.
    """
    def _aviso(msg: str) -> None:
        if aviso:
            aviso(msg)

    con = _conectar()
    filas = con.execute(
        """SELECT sitio_id, nombre, lat, lon, radio FROM sitios
           WHERE estado = 'pendiente' ORDER BY sitio_id LIMIT ?""",
        (max_sitios,)).fetchall()
    con.close()
    if not filas:
        _aviso("no hay sitios 'pendiente' (¿ya está todo enriquecido?)")
        return {"procesados": 0}

    t0 = time.perf_counter()
    contadores = {"listo": 0, "sin_dtm": 0, "error": 0}
    indice = {"i": 0}

    def _procesar(fila: sqlite3.Row) -> None:
        i = indice["i"] = indice["i"] + 1
        _aviso(f"[{i}/{len(filas)}] {fila['nombre']} "
               f"({fila['lat']:.2f}, {fila['lon']:.2f})...")
        cambios = _enriquecer_sitio(fila, aviso=_aviso)
        _guardar(cambios)
        contadores[cambios["estado"]] = \
            contadores.get(cambios["estado"], 0) + 1

    with ThreadPoolExecutor(max_workers=max(1, min(hilos, 3))) as pool:
        futuros = [pool.submit(_procesar, f) for f in filas]
        for f in as_completed(futuros):
            f.result()  # propaga excepciones no capturadas (no debería)

    contadores["segundos"] = round(time.perf_counter() - t0, 1)
    contadores["restantes_pendientes"] = _contar_pendientes()
    _aviso("enriquecido: " + json.dumps(contadores, ensure_ascii=False))
    return contadores


def _contar_pendientes() -> int:
    con = _conectar()
    n = con.execute(
        "SELECT COUNT(*) FROM sitios WHERE estado = 'pendiente'"
    ).fetchone()[0]
    con.close()
    return n


# ---------------------------------------------------------------------------
# 4. Consulta en el formato de comparación del proyecto
# ---------------------------------------------------------------------------

def sitios_disponibles(n: int | None = None, tipo: str | None = None,
                       solo_listos: bool = True) -> list[dict[str, Any]]:
    """Sitios con datos, en el formato de comparación del proyecto.

    Cada dict replica las claves del 'resumen' del registro de
    `obtener_datos_sitio()` (solo las que tienen dato) + metadatos de la
    DB (nombre, tipo, ventana THEMIS). Los consumidores (el front, el
    informe) pueden enchufar 'resumen' tal cual: mismas unidades, mismas
    claves, `via_topografia='dtm_mro'`.
    """
    sql = """SELECT * FROM sitios
             WHERE (? = 0 OR estado = 'listo')
               AND (? IS NULL OR tipo LIKE ?)
             ORDER BY nombre"""
    # Param del filtro de estado: 1 cuando solo_listos (obliga a
    # estado='listo'); 0 cuando se quieren todos (0=0 siempre verdadero).
    con = _conectar()
    filas = con.execute(
        sql, (1 if solo_listos else 0, tipo,
              f"%{tipo}%" if tipo else None)).fetchall()
    con.close()
    if n:
        filas = filas[:n]

    out = []
    for f in filas:
        # 'resumen' con EXACTAMENTE las claves del registro del proyecto;
        # se omiten las claves sin dato (como hace _resumen_para_registro).
        resumen: dict[str, Any] = {}
        if f["elevacion_media_m"] is not None:
            resumen["elevacion_media_m"] = f["elevacion_media_m"]
        if f["pendiente_media_grados"] is not None:
            resumen["pendiente_media_grados"] = f["pendiente_media_grados"]
        if f["rugosidad_media_m"] is not None:
            resumen["rugosidad_media_m"] = f["rugosidad_media_m"]
        if f["n_pixeles"] is not None:
            # mismo alias que el proyecto: en la vía DTM cuenta PÍXELES
            resumen["n_puntos_lola"] = f["n_pixeles"]
        resumen["via_topografia"] = "dtm_mro"

        extra: dict[str, Any] = {}
        for clave in ("elevacion_min_m", "elevacion_max_m",
                      "elevacion_mediana_m", "resolucion_m", "cobertura",
                      "n_crateres", "nota", "fuente_dtm", "tile_id"):
            if f[clave] is not None:
                extra[clave] = f[clave]

        mediciones: dict[str, Any] = {}
        if f["themis_n_obs"] is not None:
            mediciones = {
                "producto": THEMIS_TIPO,
                "n_total_en_caja": f["themis_n_obs"],
                "n_en_ventana": f["themis_n_ventana"],
                "ventana_ini": f["themis_ventana_ini"],
                "ventana_fin": f["themis_ventana_fin"],
            }

        out.append({
            "sitio_id": f["sitio_id"],
            "nombre": f["nombre"],
            "tipo": f["tipo"],
            "diametro_km": f["diametro_km"],
            # redondeo de presentación (la DB guarda precisión completa;
            # el sitio_id ya va redondeado y debe coincidir)
            "lat": round(f["lat"], 4),
            "lon": round(f["lon"], 4),
            "radio_grados": round(f["radio"], 3),
            "resumen": resumen,
            "topografia_extra": extra,
            "mediciones": mediciones,
            "actualizado": f["actualizado"],
        })
    return out


def estado_db() -> dict[str, Any]:
    """Conteos por estado (para el comando 'estado')."""
    con = _conectar()
    por_estado = dict(con.execute(
        "SELECT estado, COUNT(*) FROM sitios GROUP BY estado").fetchall())
    tipos = con.execute(
        "SELECT tipo, COUNT(*) FROM sitios GROUP BY tipo "
        "ORDER BY COUNT(*) DESC").fetchall()
    con.close()
    return {
        "db": str(RUTA_DB),
        "por_estado": por_estado,
        "por_tipo": {t[0]: t[1] for t in tipos},
        "total": sum(por_estado.values()),
    }


# ---------------------------------------------------------------------------
# 5. CLI
# ---------------------------------------------------------------------------

def main() -> None:
    import argparse
    import sys

    # Consola Windows: nombres con diacríticos rompen cp1252 (ver
    # carga_fondo.py): reconfigurar stdout con replace, sin entorno.
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    def _aviso(msg: str) -> None:
        print(msg, flush=True)

    parser = argparse.ArgumentParser(
        description="DB local de sitios marcianos (Gazetteer + DTM remoto "
                    "+ THEMIS). Ver docstring del módulo.")
    sub = parser.add_subparsers(dest="comando", required=True)

    sub.add_parser("indexar",
                   help="descarga el Gazetteer y crea los sitios 'pendiente'")
    p_enr = sub.add_parser(
        "enriquecer", help="calcula stats para los 'pendiente' (resumible)")
    p_enr.add_argument("--max", type=int, default=50,
                       help="cuántos sitios procesar en esta corrida")
    p_enr.add_argument("--hilos", type=int, default=2,
                       help="hilos en paralelo (2-3 máximo: cortesía ODE)")
    p_list = sub.add_parser("listar", help="sitios con datos, formato de "
                                           "comparación del proyecto")
    p_list.add_argument("--n", type=int, default=15)
    p_list.add_argument("--tipo", default=None,
                        help="filtro por tipo (p.ej. 'Mons')")
    p_list.add_argument("--todos", action="store_true",
                        help="incluir sin_dtm/error")
    p_re = sub.add_parser("reintentar",
                          help="devuelve 'error'/'sin_dtm' a 'pendiente'")
    p_re.add_argument("--todo", action="store_true",
                      help="también los sin_dtm (p.ej. si cambió el radio)")
    sub.add_parser("estado", help="conteos por estado y tipo")

    args = parser.parse_args()
    if args.comando == "indexar":
        indexar_gazetteer(aviso=_aviso)
    elif args.comando == "enriquecer":
        enriquecer(max_sitios=args.max, hilos=args.hilos, aviso=_aviso)
    elif args.comando == "listar":
        lista = sitios_disponibles(n=args.n, tipo=args.tipo,
                                   solo_listos=not args.todos)
        print(json.dumps(lista, ensure_ascii=False, indent=1))
    elif args.comando == "reintentar":
        con = _conectar()
        estados = ("error", "sin_dtm") if args.todo else ("error",)
        cur = con.execute(
            f"UPDATE sitios SET estado = 'pendiente', error = NULL "
            f"WHERE estado IN ({','.join('?' * len(estados))})", estados)
        con.commit()
        con.close()
        _aviso(f"{cur.rowcount} sitios vueltos a 'pendiente'")
    elif args.comando == "estado":
        print(json.dumps(estado_db(), ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
