"""Análogos terrestres — los mismos parámetros medidos en la TIERRA.

El reto pide comparar el sitio lunar/marciano con lugares de la Tierra, así
que este módulo trae el "lado terrestre" de la comparación usando CMR
(Earthdata) y GIBS de `nsac.sources.earthdata`:

  - elevación           -> ASTER Global DEM / SRTM (colecciones CMR)
  - temperatura         -> MODIS Land Surface Temperature
  - albedo/reflectancia -> colecciones de albedo/BRDF
  - humedad             -> SMAP (análogo del hielo de los PSR)
  - teselas GIBS        -> URLs listas para el visor (Leaflet/MapLibre)

Coste: 4 llamadas CMR (una por variable) + 1 llamada al catálogo GIBS
(cacheada dentro de nsac). Es opcional: solo se ejecuta cuando se pide
`incluir_tierra=True` o se llama a `datos_tierra` directamente.
"""

from __future__ import annotations

from typing import Any

from . import constantes, utilidades


def datos_tierra(lat: float, lon: float, radio: float = 0.5) -> dict[str, Any]:
    """Catálogo de datos terrestres disponibles para el punto (lat, lon).

    No descarga rásteres (eso necesita Earthdata Login): busca qué colecciones
    cubren el sitio y devuelve sus concept_id para que la app pueda pedir
    granules después. Es el espejo terrestre de los parámetros del sitio
    lunar/marciano, con las MISMAS claves para compararlos.
    """
    from nsac.sources import copernicus, earthdata

    bbox = utilidades.caja_stac(lat, lon, radio)  # (oeste, sur, este, norte)
    seccion: dict[str, Any] = {
        "nota": "Catálogo CMR: nombres/ids de colecciones que cubren el sitio.",
    }

    # --- 1) una llamada CMR por variable (4 en total) ----------------------
    for variable, palabra in constantes.VARIABLES_CMR:
        try:
            colecciones = earthdata.search_collections(keyword=palabra,
                                                       page_size=5)
            seccion[variable] = [
                {
                    "nombre_corto": c.get("short_name"),
                    "titulo": c.get("title"),
                    "concept_id": c.get("concept_id"),  # pásalo a search_granules
                    "cobertura_temporal": f"{c.get('start')} .. {c.get('end')}",
                }
                for c in colecciones[:3]
            ]
        except Exception as exc:
            seccion[variable] = {"error": str(exc)}

    # --- 2) capas GIBS para el visor (1 llamada, cacheada en nsac) ---------
    try:
        gibs = []
        for palabra in ("true color", "land surface temperature"):
            gibs += [
                {"id": c["id"], "titulo": c["title"], "formato": c["format"]}
                for c in earthdata.search_gibs_layers(palabra)[:3]
            ]
        seccion["teselas_gibs"] = gibs
    except Exception as exc:
        seccion["teselas_gibs"] = {"error": str(exc)}

    # --- 3) Sentinel-2 de Copernicus (óptico, 1 llamada STAC) --------------
    # Sentinel-2 solo cubre latitudes entre ±82°. Si el punto está más allá
    # (p.ej. el cráter Shackleton, a -89.9°), el recorte produciría una caja
    # gigante que Copernicus rechaza con un 400: en ese caso NO se consulta
    # y se lo decimos claro. Si solo se pasa un poquito, basta con recortar.
    oeste, sur, este, norte = bbox
    sur_s2, norte_s2 = max(sur, -82.0), min(norte, 82.0)
    seccion["sentinel2"] = {"nota": "el punto queda fuera de la cobertura de "
                                    "Sentinel-2 (±82° de latitud)"}
    # Si tras recortar la caja quedó invertida (sur >= norte), el punto está
    # TOTALMENTE fuera de cobertura: nos quedamos con la nota explicativa.
    # Si quedó enorme (parcial fuera), Copernicus la rechazaría con 400:
    # también evitamos la consulta y explicamos.
    if 0.0 < norte_s2 - sur_s2 <= 40.0:
        try:
            escenas = copernicus.search_stac(["sentinel-2-l1c"],
                                             bbox=(oeste, sur_s2, este, norte_s2),
                                             limit=3)
            seccion["sentinel2"] = [
                {"id": e.get("id"),
                 "fecha": e.get("datetime"),
                 "nubes_pct": e.get("cloud_cover")}
                for e in escenas
            ]
        except Exception as exc:
            seccion["sentinel2"] = {"error": str(exc)}

    return seccion
