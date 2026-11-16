"""Topografía — elevación, pendiente, rugosidad y cráteres/formaciones.

Fuentes (en orden de uso, de más barata a más cara):
  1. PDS GDS  (`lolardr`): nube de puntos de LOLA (lat, lon, radio del punto).
     UNA consulta da elevación; pendiente, rugosidad y candidatos a cráter se
     CALCULAN localmente con `utilidades`, sin más llamadas.
  2. USGS STAC: los DTM de alta resolución (Kaguya TC en la Luna, HiRISE/CTX
     en Marte). Solo metadatos+URL: para análisis fino se descarga aparte.
  3. Treks: capas ya renderizadas (DEM, pendiente, rugosidad) para el visor.

Solo la función `elevacion_lola` habla con la red (1 llamada GDS por caja).
"""

from __future__ import annotations

from typing import Any

from . import constantes, utilidades


# ---------------------------------------------------------------------------
# 1. Elevación puntual: LOLA vía PDS GDS (solo Luna)
# ---------------------------------------------------------------------------

def elevacion_lola(cajas: list[tuple[float, float, float, float]]) -> dict[str, Any]:
    """Baja los puntos LOLA dentro de cada caja GDS y resume la elevación.

    `cajas` viene de `utilidades.cajas_gds(...)` (una o dos cajas si el área
    cruza el meridiano 0). Cada caja es 1 llamada; normalmente es solo 1.

    Devuelve un dict con:
      - 'puntos': lista de {lat, lon, radio_m} (la usan pendiente/rugosidad/
        cráteres: las tres cosas salen de ESTA MISMA descarga).
      - 'elevacion_m': estadísticas (media, min, max...) relativas al datum.
      - 'errores': qué cajas fallaron, si alguna.
    """
    import pandas as pd
    from . import cache_gds

    # Cada caja pasa por la caché local: la 1ª vez baja del GDS (minutos),
    # las siguientes se leen del disco (milisegundos). Los datos LOLA son
    # históricos: re-bajarlos daría lo mismo.
    frames: list[Any] = []
    errores: list[str] = []
    for caja in cajas:
        try:
            # 'lolardr' = LRO LOLA RDR: un punto por disparo del láser.
            df_caja, _ruta, _cache = cache_gds.leer_o_descargar("lolardr", caja)
            frames.append(df_caja)
        except Exception as exc:
            errores.append(f"caja {caja}: {exc}")

    if not frames:
        return {"error": "; ".join(errores) or "sin datos"}

    df = pd.concat(frames, ignore_index=True)

    # Cada fila del GDS LOLA es un "frame" con 5 disparos (detectores D1..D5),
    # cada uno con su lat/lon/radio de superficie. Los ecos perdidos vienen
    # como -99 (radio) y 999 (longitud): hay que filtrarlos. NOTA: si tomamos
    # solo una columna 'radio' por nombre, caeríamos en 'SC_radius' (la nave,
    # ~50 km por encima del suelo), por eso se recorren los detectores a mano.
    puntos = []
    for d in range(1, 6):
        c_lat, c_lon, c_rad = f"D{d}_Latitude", f"D{d}_Longitude", f"D{d}_Radius"
        if not all(c in df.columns for c in (c_lat, c_lon, c_rad)):
            continue  # un dataset sin los 5 detectores sigue siendo útil
        sub = df[[c_lat, c_lon, c_rad]].apply(pd.to_numeric, errors="coerce")
        for lat, lon, rad in sub.itertuples(index=False):
            if not (rad > 0):          # -99 = disparo sin eco válido
                continue
            lat, lon = float(lat), float(lon)
            if not (-90.0 <= lat <= 90.0) or lon > 900.0:
                continue               # lat/lon basura (999...)
            # El GDS usa el convenio 0-360: lo normalizamos a [-180, 180]
            # para que las distancias y la proyección local sean coherentes.
            lon = ((lon + 180.0) % 360.0) - 180.0
            # El radio viene en KILÓMETROS (~1737.6); lo pasamos a metros.
            # Un radio planetario real jamás baja de 50.000 km, así que el
            # umbral distingue km de m sin ambigüedad.
            radio_m = rad * 1000.0 if rad < 50000.0 else rad
            puntos.append({"lat": lat, "lon": lon, "radio_m": radio_m})

    if not puntos:
        return {"error": "ningún punto LOLA válido en la caja (todo -99?)",
                "errores": errores}

    # Elevación = distancia al centro del cuerpo menos el radio de referencia.
    # Si el CSV trae la columna 'Geoid' (radio del areoide local, km), la
    # usamos como datum: es físicamente más correcto que el esferoide medio.
    if "Geoid" in df.columns:
        geoid_km = pd.to_numeric(df["Geoid"], errors="coerce").dropna()
        datum_m = float(geoid_km.mean()) * 1000.0
        origen_datum = "areoide local (columna Geoid del propio GDS)"
    else:
        datum_m = constantes.RADIO_DATUM_LUNA_M
        origen_datum = "esferoide medio (1 737 400 m)"
    elevaciones = [p["radio_m"] - datum_m for p in puntos]

    # Filtro robusto de ecos malos: el GDS a veces devuelve un radio con
    # decenas de km de error (ruido del láser, eco de la propia nave). Con la
    # desviación absoluta mediana (MAD) descartamos lo que se aleje mucho de
    # la mediana sin que un solo punto extremo la dispare, como haría la media.
    # Umbral = max(8×MAD, 500 m): 500 m cubre cajas minúsculas donde MAD≈0.
    if len(elevaciones) >= 10:
        mediana = sorted(elevaciones)[len(elevaciones) // 2]
        mad = sorted(abs(e - mediana) for e in elevaciones)[len(elevaciones) // 2]
        umbral = max(8.0 * mad, 500.0)
        antes = len(puntos)
        parejas = [(p, e) for p, e in zip(puntos, elevaciones)
                   if abs(e - mediana) <= umbral]
        if parejas:
            puntos = [p for p, _ in parejas]
            elevaciones = [e for _, e in parejas]
            descartados = antes - len(puntos)
        else:
            descartados = 0
    else:
        descartados = 0

    return {
        "fuente": "LRO LOLA RDR vía PDS GDS",
        "n_puntos": len(puntos),
        "puntos_descartados_outlier": descartados,
        "datum": {"valor_m": round(datum_m, 1), "origen": origen_datum},
        "elevacion_m": utilidades.estadisticas(elevaciones),
        "puntos": puntos,
        "errores": errores,
    }


# ---------------------------------------------------------------------------
# 2. DTM de alta resolución disponibles (USGS STAC, 1 llamada)
# ---------------------------------------------------------------------------

def dtm_disponibles(cuerpo: str, bbox_stac: tuple[float, float, float, float],
                    lat: float) -> list[dict[str, Any]]:
    """Busca DTM/mosaicos que cubran el sitio en el STAC de USGS Astrogeology.

    Una única llamada POST /search con TODAS las colecciones interesantes a
    la vez (polares o globales según la latitud del sitio). Devuelve, por
    cada producto, la URL del mejor raster (`best_asset`), lista para
    descargar o para abrir con rasterio/GDAL, MÁS el bbox del item: con él
    se puede elegir el tile que de verdad cubre la caja (los tiles Kaguya
    son franjas/cuadrantes y en una caja pueden solaparse varios).

    La búsqueda pasa por la caché de catálogos (cache_catalogo): el mismo
    sitio no necesita re-consultar el STAC en cada corrida (ahorra ~2-3 s
    por consulta y una llamada al servidor).
    """
    from nsac.sources import usgs_stac
    from . import cache_catalogo

    if cuerpo == "mars":
        colecciones = constantes.COLECCIONES_STAC["marte"]
    elif abs(lat) >= 80:
        clave = "luna_polo_sur" if lat < 0 else "luna_polo_norte"
        colecciones = constantes.COLECCIONES_STAC[clave]
    else:
        colecciones = constantes.COLECCIONES_STAC["luna_global"]

    # Clave de caché legible: cuerpo + banda de colecciones + caja redondeada.
    # (El redondeo a 3 decimales evita duplicar entradas por ruido flotante;
    #  0.001° ≈ 30 m: exactitud sobrada para elegir tiles de km.)
    o, s, e, n = (round(v, 3) for v in bbox_stac)
    limpio = lambda v: f"{v:.3f}".replace("-", "m").replace(".", "p")
    nombre_cache = (f"stac_dtm_{cuerpo}_{'sur' if lat < 0 else 'norte' if abs(lat) >= 80 else 'global'}"
                    f"_{limpio(o)}_{limpio(s)}_{limpio(e)}_{limpio(n)}")

    def _buscar() -> list[dict[str, Any]]:
        items = usgs_stac.search(colecciones, bbox=(o, s, e, n), limit=10)
        return [
            {
                "id": it.get("id"),
                "bbox": it.get("bbox"),
                "fecha": it.get("datetime"),
                "url_mejor_asset": usgs_stac.best_asset(it),
            }
            for it in items
        ]

    items, _de_cache = cache_catalogo.json_o_red(nombre_cache, _buscar)
    return items


# ---------------------------------------------------------------------------
# 3. Capas de Treks relacionadas con la topografía (0 llamadas extra)
# ---------------------------------------------------------------------------

def capas_topografia_trek(capas: list[dict[str, Any]]) -> dict[str, Any]:
    """Del catálogo Treks ya bajado, extrae las capas de DEM, pendiente,
    rugosidad y cráteres. Sirven para el visor y como referencia de
    resolución. No gasta llamadas: solo filtra en memoria."""
    pc = constantes.PALABRAS_CLAVE_CAPAS
    return {
        "dem": utilidades.capas_por_keyword(capas, pc["dem"]),
        "pendiente": utilidades.capas_por_keyword(capas, pc["pendiente"]),
        "rugosidad": utilidades.capas_por_keyword(capas, pc["rugosidad"]),
        "crateres": utilidades.capas_por_keyword(capas, pc["crateres"]),
        "geologia": utilidades.capas_por_keyword(capas, pc["geologia"]),
        "nota_formaciones": (
            "Formaciones geológicas: ver el mapa geológico unificado (USGS) y "
            "las capas 'geologia'. El mapeo fino se hace con el DTM descargable."
        ),
    }
