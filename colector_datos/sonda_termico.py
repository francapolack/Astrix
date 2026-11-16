"""sonda_termico.py — Sonda del paso 2 (rama `tierra-datos-crudos`).

Preguntas que responde ANTES de codificar el módulo térmico:
  1. ¿Qué colecciones MODIS LST existen y cuál es su concept_id (CMR)?
  2. ¿La búsqueda de granules funciona sin credenciales y qué URL de
     descarga devuelve? (¿están tras Earthdata Login?)
  3. ¿Qué formato tienen los ficheros (HDF4/NetCDF) y los puede leer
     rasterio de esta instalación sin dependencias extra?
  4. ¿Qué otros candidatos hay: VIIRS LST (VNP21), ERA5 en AWS abierto?

Ejecutar desde la raíz:  python -m colector_datos.sonda_termico
"""

import time


def _crono(etiqueta, fn):
    t0 = time.perf_counter()
    try:
        out = fn()
        print(f"  {etiqueta}: {time.perf_counter() - t0:.1f}s")
        return out
    except Exception as exc:
        print(f"  {etiqueta}: FALLO {exc} ({time.perf_counter() - t0:.1f}s)")
        return None


def sondear() -> None:
    from nsac.sources import earthdata

    print("=== 1) colecciones MODIS/VIIRS LST en CMR ===")
    colls = _crono("search_collections 'land surface temperature'",
                   lambda: earthdata.search_collections(
                       keyword="land surface temperature", page_size=10))
    if colls:
        for c in colls:
            print(f"    {c['short_name']:14} {c['concept_id']}  "
                  f"{c['start']}..{c['end'] or 'presente'}")

    # MOD11A2 (MODIS Terra LST 8-días, 1 km) suele ser la más estable.
    cid = None
    for c in (colls or []):
        if c["short_name"] in ("MOD11A2", "MOD11A2.061"):
            cid = c["concept_id"]
            break
    if cid is None and colls:
        cid = colls[0]["concept_id"]
    print(f"    elegida: {cid}")

    print("=== 2) granules sin credenciales (Death Valley, 2024-07) ===")
    granules = _crono("search_granules MOD11A2",
                      lambda: earthdata.search_granules(
                          cid, bbox=(-117.2, 36.4, -117.0, 36.6),
                          temporal="2024-07-01,2024-07-31", page_size=5))
    if granules:
        for g in granules:
            print(f"    {g['granule_id']} {g['size_mb']} MB")
            for u in g["download"]:
                print(f"      -> {u}")

    print("=== 3) ¿rasterio lee el granule (HDF4/NetCDF)? ===")
    # Descarga SIN auth del primer enlace (si es público; si no, 401)
    if granules and granules[0]["download"]:
        import requests
        url = granules[0]["download"][0]
        r = _crono(f"GET {url.rsplit('/', 1)[-1]}",
                   lambda: requests.get(url, timeout=60, stream=True))
        if r is not None and r.status_code == 200:
            ruta = "data/cache/sonda_termico." + url.rsplit(".", 1)[-1]
            with open(ruta, "wb") as f:
                for chunk in r.iter_content(1 << 20):
                    f.write(chunk)
            import rasterio
            try:
                with rasterio.open(ruta) as src:
                    print(f"    rasterio OK: driver={src.driver} "
                          f"subdatasets={len(src.subdatasets)} "
                          f"res={src.res} crs={src.crs}")
                    for sd in src.subdatasets[:6]:
                        print(f"      {sd.rsplit(':', 1)[-1]}")
            except Exception as exc:
                print(f"    rasterio NO lee: {exc}")
        elif r is not None:
            print(f"    descarga HTTP {r.status_code}: requiere Earthdata Login")

    print("=== 4) VIIRS VNP21A2 y ERA5-AWS (candidatos alternos) ===")
    vnp = _crono("search_collections 'VIIRS land surface temperature'",
                 lambda: earthdata.search_collections(
                     keyword="VIIRS land surface temperature", page_size=5))
    for c in (vnp or [])[:3]:
        print(f"    {c['short_name']:14} {c['concept_id']}")


if __name__ == "__main__":
    sondear()
