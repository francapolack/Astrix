"""prueba_funcion.py — prueba la función principal y explica los resultados.

Ejecútalo desde la raíz del proyecto:

    python -m colector_datos.prueba_funcion                      # default: Extranio (Gale)
    python -m colector_datos.prueba_funcion --sitio malapert     # presets
    python -m colector_datos.prueba_funcion --cuerpo marte --lat 18.4 --lon 77.6
    python -m colector_datos.prueba_funcion --lat -86.0 --lon 0.7 --radio 0.2
    python -m colector_datos.prueba_funcion --cuerpo tierra --lat 12.3 --lon 45.6

Las consultas de datos crudos (GDS de PDS) tardan MINUTOS: es lo normal.

Cada consulta queda REGISTRADA en `data/registro_sitios.json`: el registro
guarda una entrada por sitio (clave cuerpo@lat,lon±radio) con la fecha, un
resumen de los números principales y el diccionario completo. Si vuelves a
consultar el mismo sitio, su entrada se actualiza con la nueva fecha.

Este script NO añade ninguna fuente de datos nueva: solo llama a
`obtener_datos_sitio(...)` y traduce el diccionario a un informe legible,
diciendo para cada número:
  - qué ES (concepto físico),
  - en QUÉ unidad viene,
  - si es BUENO o MALO para poner una base (criterios del reto).

Es la versión "para humanos" del volcado JSON crudo.
"""

from __future__ import annotations

import argparse

from . import constantes
from .api import obtener_datos_sitio


# ---------------------------------------------------------------------------
# Utilidades de impresión (nada de lógica de datos aquí)
# ---------------------------------------------------------------------------

def barra(titulo: str) -> None:
    """Imprime un separador de sección con título, p.ej. '=== TOPOGRAFÍA ==='."""
    print("\n" + "=" * 72)
    print(f"  {titulo}")
    print("=" * 72)


def linea(clave: str, valor, nota: str = "") -> None:
    """Imprime 'clave: valor' con una nota opcional alineada a la derecha."""
    texto = f"  {clave:38} {str(valor)}"
    if nota:
        texto += f"   ({nota})"
    print(texto)


def kelvin_a_celsius(k: float) -> float:
    """Conversión obvia, para que los números 'hablen' (121 K = -152 °C)."""
    return round(k - 273.15, 1)


def mostrar_estadistica(nombre: str, stats, unidad: str,
                        como_leer: str = "") -> None:
    """Imprime un bloque estadístico {n, min, max, media, ...} con explicación.

    `stats` es el dict que devuelve `utilidades.estadisticas` (o None, o un
    dict con 'nota'/'error' si no hubo datos). La función tolera los tres
    casos para que el informe no se rompa a la mitad.
    """
    print(f"\n  · {nombre}")
    if stats is None:
        print("    (sin datos para este parámetro en esta caja)")
        return
    if "error" in stats:
        print(f"    ERROR: {stats['error']}")
        return
    if "nota" in stats and "media" not in stats:
        print(f"    {stats['nota']}")
        return

    n = stats.get("n")
    print(f"    muestras usadas : {n}")
    print(f"    mínimo          : {stats['min']:>12} {unidad}")
    print(f"    media           : {stats['media']:>12} {unidad}")
    print(f"    mediana         : {stats['mediana']:>12} {unidad}")
    print(f"    máximo          : {stats['max']:>12} {unidad}")
    print(f"    desviación típ. : {stats['desv_estandar']:>12} {unidad} "
          "(cuánto varía de punto a punto)")
    if como_leer:
        print(f"    cómo leerlo     : {como_leer}")


def clasifica(valor: float, umbrales: list[tuple[float, str, str]]) -> str:
    """Devuelve el texto del primer umbral que cumple el valor.

    `umbrales` es una lista de (límite, etiqueta_buena, etiqueta_mala);
    p.ej. [(7, 'FAVORABLE: terreno llano', 'INCLINADO: exige terrazas')].
    """
    for limite, si_bajo, si_alto in umbrales:
        if valor <= limite:
            return "✓ " + si_bajo
        return "⚠ " + si_alto
    return ""


def motivo_sin_datos(valor: object, pista: str = "") -> str:
    """Traduce un valor ausente a una frase que explica el PORQUÉ.

    Los módulos de datos marcan el fallo de dos maneras:
      - como TEXTO: el mensaje de error de la fuente (p.ej. red caída);
      - como DICT con 'nota': una explicación ya redactada (p.ej. fuera
        de cobertura del instrumento).
    Si no hay ninguno de los dos, se muestra la `pista` genérica.
    """
    if isinstance(valor, str) and valor:
        return f"falló la consulta → {valor[:180]}"
    if isinstance(valor, dict):
        if valor.get("error"):
            return f"falló la consulta → {str(valor['error'])[:180]}"
        if valor.get("nota"):
            return valor["nota"]
    return pista or "sin datos"


# ---------------------------------------------------------------------------
# Secciones del informe (una función por sección del diccionario)
# ---------------------------------------------------------------------------

def mostrar_topografia(t: dict) -> None:
    barra("TOPOGRAFÍA  (¿se puede aterrizar y circular aquí?)")
    print("  Fuente: " + (t.get("fuente")
          or "puntos del láser LOLA (NASA LRO) + DTM Kaguya (USGS)."))

    elev = t.get("elevacion_m")
    if isinstance(elev, dict) and "media" in elev:
        mostrar_estadistica(
            "ELEVACIÓN", elev, "m",
            "altura sobre el nivel de referencia del cuerpo. Solo sirve para "
            "comparar entre sitios: no hay 'mejor' elevación absoluta.")
    elif t.get("nota_elevacion"):
        # Marte no tiene servicio tipo GDS: la elevación puntual exige un DTM.
        print(f"  Elevación: sin datos puntuales → {t['nota_elevacion']}")
    else:
        print("  Elevación: sin datos → "
              + motivo_sin_datos(elev, "la caja no atrapó puntos LOLA: "
              "prueba un radio mayor, o mira dtm_descargables"))

    pend = t.get("pendiente")
    if isinstance(pend, dict) and "media" in pend:
        mostrar_estadistica(
            "PENDIENTE DEL TERRENO", pend, "grados",
            "0° = plano como una mesa; <7° apto para aterrizar; >15° = "
            "peligroso para rovers y edificios.")
        print(f"    veredicto       : {clasifica(pend['media'], [(7, 'FAVORABLE: terreno llano', 'INCLINADO: exige trabajos de nivelación')])}")
    else:
        linea("pendiente", "sin datos", pend.get("nota", "") if isinstance(pend, dict) else "")

    rugo = t.get("rugosidad")
    if isinstance(rugo, dict) and "media" in rugo:
        mostrar_estadistica(
            "RUGOSIDAD SUPERFICIAL", rugo, "m",
            "desviación típica de la altura dentro de celdas de 100 m. "
            "<1 m liso; 1-5 m moderado; >5 m = bloques y ondulaciones.")
        print(f"    veredicto       : {clasifica(rugo['media'], [(5, 'MANEJABLE', 'RUGOSO: riesgo de aterrizaje')])}")
    else:
        linea("rugosidad", "sin datos", "")

    crat = t.get("crateres_formaciones") or {}
    print(f"\n  · CRÁTERES / FORMACIONES (detección aproximada)")
    print(f"    método          : {crat.get('metodo', '-')}")
    print(f"    candidatos      : {crat.get('n_candidatos', 0)} "
          "(profundidad estimada, en metros; con cajas pequeñas es normal 0)")
    for c in (crat.get("candidatos") or [])[:5]:
        print(f"      - lat {c['lat']:>9}  lon {c['lon']:>9}  "
              f"profundidad ≈ {c['profundidad_est_m']} m")
    print("    cómo leerlo     : un cráter cercano es a la vez riesgo "
          "(relieves) y recurso (sombra permanente = posible hielo).")

    print(f"\n  · DTM DESCARGABLES (mapas de elevación de alta resolución):")
    dtms = t.get("dtm_descargables")
    if isinstance(dtms, list):
        for d in dtms[:3]:
            print(f"      - {d.get('id')}")
            print(f"        {d.get('url_mejor_asset')}")
    else:
        # Puede ser un dict de error (p.ej. el catálogo STAC no respondió):
        # se muestra el motivo en vez de romper el informe.
        print(f"      - {motivo_sin_datos(dtms, 'sin catálogo DTM para esta caja')}")


def mostrar_termico(t: dict) -> None:
    barra("TÉRMICA  (¿cuánto frío/calor tendremos que aguantar?)")
    print("  Fuente: " + (t.get("fuente")
          or "radiómetro Diviner (NASA LRO), canales térmicos 3-9."))

    temp = t.get("temperatura_superficial")
    if isinstance(temp, dict) and "media" in temp:
        mostrar_estadistica(
            "TEMPERATURA SUPERFICIAL", temp, "K",
            "en grados Celsius: min "
            f"{kelvin_a_celsius(temp['min'])} °C · media "
            f"{kelvin_a_celsius(temp['media'])} °C · max "
            f"{kelvin_a_celsius(temp['max'])} °C. La 'temperatura de brillo' "
            "de Diviner es la mejor medida de la temperatura REAL del suelo.")
        print(f"    veredicto       : media "
              f"{kelvin_a_celsius(temp['media'])} °C → "
              + ("FRÍO EXTREMO: aislamiento y calefacción críticos"
                 if temp["media"] < 200 else "MODERADO para el cuerpo"))
    else:
        # Marte no tiene GDS: su sección trae una 'nota' que lo explica.
        if t.get("nota"):
            print(f"  Temperatura: sin datos crudos → {t['nota']}")
        else:
            fallo = t.get("error") or temp
            print("  Temperatura: sin datos → "
                  + motivo_sin_datos(fallo, "repite la consulta: el GDS a "
                  "veces se traba, o la caja no atrapó observaciones"))

    dn = t.get("dia_noche")
    if isinstance(dn, dict) and "diferencia_k" in dn:
        print(f"\n  · DIFERENCIA DÍA/NOCHE")
        print(f"    media de día    : {dn['media_dia_k']} K "
              f"({kelvin_a_celsius(dn['media_dia_k'])} °C)")
        print(f"    media de noche  : {dn['media_noche_k']} K "
              f"({kelvin_a_celsius(dn['media_noche_k'])} °C)")
        print(f"    amplitud        : {dn['diferencia_k']} K "
              "(cuanto MENOR, más estable: mejor para equipos y hábitats)")
    else:
        print("\n  · Diferencia día/noche: sin datos")

    est = t.get("variacion_estacional")
    if isinstance(est, dict) and "variacion_k" in est:
        print(f"\n  · VARIACIÓN ESTACIONAL (12 meses del año lunar)")
        print(f"    variación total : {est['variacion_k']} K entre el mes más "
              "frío y el más cálido")
        for mes, valor in (est.get("media_por_mes_k") or {}).items():
            print(f"      mes {mes}: {valor:>7} K  "
                  f"({kelvin_a_celsius(valor)} °C)")
        print("    cómo leerlo     : la Luna tarda ~1 año en rodear el Sol; "
              "el 'invierno' del polo sur es cuando el Sol está más bajo.")
    else:
        print("\n  · Variación estacional: "
              + (est.get("nota") if isinstance(est, dict) else "sin datos"))


def mostrar_superficie(s: dict) -> None:
    barra("SUPERFICIE  (¿de qué está hecho el suelo?)")

    refl = s.get("reflectancia_albedo")
    if isinstance(refl, dict) and "media" in refl:
        mostrar_estadistica(
            "REFLECTANCIA / ALBEDO", refl, "0-1",
            "fracción de luz solar que el suelo devuelve. Alto = claro "
            "(tierras altas, regolito fresco); bajo = oscuro (mares de "
            "basalto, polvo maduro).")
    else:
        linea("reflectancia/albedo", "sin datos", "")

    roca = s.get("tipo_roca")
    if roca:
        print(f"\n  · TIPO DE ROCA (inferido del albedo, heurística)")
        print(f"    clasificación   : {roca.get('clasificacion')}")
        print(f"    cómo leerlo     : {roca.get('metodo')}")

    miner = s.get("minerales_predominantes") or {}
    print(f"\n  · MINERALES PREDOMINANTES (capas disponibles para el mapa):")
    for capa in (miner.get("capas_trek") or [])[:4]:
        print(f"      - {capa['id']}  ({capa.get('titulo')})")
    for b in (miner.get("bundles_pds") or [])[:3]:
        if "error" in b:
            print(f"      - PDS: {b['error']}")
        else:
            print(f"      - PDS: {b.get('titulo')}")

    polvo = s.get("materiales_y_polvo") or {}
    if polvo.get("capas_trek"):
        print(f"\n  · MATERIALES SUPERFICIALES / POLVO (capas):")
        for capa in polvo["capas_trek"][:4]:
            print(f"      - {capa['id']}")
    print(f"\n  · nota regolito  : {polvo.get('nota', '-')}")


def mostrar_iluminacion(i: dict) -> None:
    barra("ILUMINACIÓN Y ENERGÍA  (¿cuánta luz solar gratis hay?)")

    for capa in (i.get("capas_iluminacion") or [])[:4]:
        print(f"  · capa de iluminación: {capa['id']}  ({capa.get('titulo')})")

    energ = i.get("energia_solar") or {}
    print(f"\n  · ENERGÍA SOLAR RECIBIDA")
    print(f"    constante solar : {energ.get('constante_solar_wm2')} W/m² "
          "(potencia del Sol a la distancia de la Tierra/Luna)")
    if "energia_media_estimada_wm2" in energ:
        e = energ["energia_media_estimada_wm2"]
        print(f"    estimación media: {e} W/m²  "
              f"= {round(e / 1361 * 100)}% del máximo teórico")
        print(f"    cómo leerlo     : 1000 W/m² en paneles ≈ 200-300 W "
              "eléctricos reales; en el polo lunares varía con la estación.")
    else:
        print(f"    nota            : {energ.get('nota')}")

    psr = i.get("zonas_sombra_psr") or {}
    print(f"\n  · ZONAS EN SOMBRA PERMANENTE (PSR):")
    for capa in (psr.get("capas") or [])[:4]:
        print(f"      - {capa['id']}  ({capa.get('titulo')})")
    print(f"    cómo leerlo     : {psr.get('nota', '-')}")


# ---------------------------------------------------------------------------
# Programa principal
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Prueba obtener_datos_sitio() y explica su diccionario.")
    parser.add_argument("--sitio", default="Extranio",
                        choices=list(constantes.SITIOS),
                        help="sitio de constantes.SITIOS a caracterizar")
    parser.add_argument("--cuerpo", default=None,
                        choices=["luna", "marte", "tierra"],
                        help="cuerpo para coordenadas propias (con --lat --lon)")
    parser.add_argument("--lat", type=float, default=None,
                        help="latitud propia (junto a --lon)")
    parser.add_argument("--lon", type=float, default=None,
                        help="longitud propia (junto a --lat)")
    parser.add_argument("--radio", type=float, default=None,
                        help="semiancho de la caja en grados (por defecto el del sitio, o 0.05)")
    parser.add_argument("--sin_dtm", action="store_true",
                        help="fuerza la topografía por GDS LOLA aunque el DTM "
                             "de Kaguya cubra la caja (comparación A/B de vías)")
    args = parser.parse_args()

    # Se decide el sitio: coordenadas propias si el usuario las dio,
    # si no, uno de los presets de constantes.SITIOS.
    if args.lat is not None or args.lon is not None:
        if args.lat is None or args.lon is None:
            parser.error("para coordenadas propias hay que dar --lat Y --lon")
        cuerpo, lat, lon = args.cuerpo or "luna", args.lat, args.lon
        radio = args.radio if args.radio is not None else 0.05
        descripcion = f"coordenadas propias (cuerpo: {cuerpo})"
    else:
        sitio = constantes.SITIOS[args.sitio]
        cuerpo, lat, lon = sitio["cuerpo"], sitio["lat"], sitio["lon"]
        radio = args.radio if args.radio is not None else sitio["radio"]
        descripcion = sitio["nota"]

    print("\n" + "#" * 72)
    print("#  INFORME DE SITIO — NSAC (NASA Space Apps 2026)")
    print("#")
    print(f"#  Sitio elegido : {cuerpo}  lat {lat}  lon {lon}  caja ±{radio}°")
    print(f"#  Descripción   : {descripcion}")
    print("#")
    print("#  Qué vas a ver: el diccionario de obtener_datos_sitio() traducido")
    print("#  a un informe: cada número con su unidad y su lectura para el reto.")
    print("#")
    print("#  La consulta queda registrada en colector_datos/data/")
    print("#" * 72)

    print("\nConsultando fuentes... (Treks y STAC responden en segundos; los")
    print("CSV crudos del GDS de PDS tardan VARIOS MINUTOS por consulta, y")
    print("cuanto más grande es la caja, más tardan. No cortes el proceso.)")
    import time
    t0 = time.time()

    datos = obtener_datos_sitio(
        cuerpo=cuerpo,
        lat=lat,
        lon=lon,
        radio=radio,
        usar_gds=True,       # siempre completo: los GDS traen los datos crudos
        usar_dtm=not args.sin_dtm,  # --sin_dtm = topografía por GDS LOLA
        aviso=print,         # informa cada etapa (las GDS tardan varios minutos)
    )

    print(f"Listo en {round(time.time() - t0)} s.\n")

    barra("METADATOS  (de dónde salieron los datos)")
    m = datos.get("metadatos", {})
    for fuente in m.get("fuentes", []):
        print(f"  · {fuente}")
    print(f"  · registro      : {m.get('registro', 'no se guardó')}")

    if cuerpo != "tierra":
        # Las secciones de abajo son para Luna/Marte; en Tierra el bloque
        # útil es el de análogos (se muestra tras esta comprobación).
        mostrar_topografia(datos.get("topografia", {}))
        mostrar_termico(datos.get("termico", {}))
        mostrar_superficie(datos.get("superficie", {}))
        mostrar_iluminacion(datos.get("iluminacion", {}))

    if "analogos_tierra" in datos:
        # Cuando el cuerpo es 'tierra', lo que baja es el catálogo de
        # análogos terrestres (CMR/GIBS/Copernicus); se muestra con el
        # presentador que ya existe en prueba_tierra.py.
        from .prueba_tierra import mostrar_tierra
        barra("ANÁLOGOS TIERRA  (catálogo de datasets terrestres)")
        mostrar_tierra(datos["analogos_tierra"], lat, lon)

    barra("CÓMO USAR ESTO EN LA COMPETENCIA")
    print("  1. Cada bloque de arriba = un criterio del enunciado")
    print("     (topografía, geología, ambiente, recursos).")
    print("  2. Convierte cada número en un score 0-1 (p.ej. menos pendiente")
    print("     = más puntos) y compáralo con sitios TERRESTRES: con")
    print("     incluir_tierra=True la función también baja CMR/GIBS con las")
    print("     mismas variables para Atacama, Antártida, etc.")
    print("  3. El sitio terrestre con el vector más parecido es tu ANÁLOGO:")
    print("     allí se prueba el hardware antes de enviarlo.")


if __name__ == "__main__":
    main()
