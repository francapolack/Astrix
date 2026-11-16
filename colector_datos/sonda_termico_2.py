"""sonda_termico_2.py — sonda térmica enfocada a MODIS LP DAAC (paso 2)."""

import time


def main() -> None:
    from nsac.sources import earthdata

    print("=== colecciones por short_name ===")
    for kw in ("MOD11A2", "VNP21A2"):
        colls = earthdata.search_collections(keyword=kw, page_size=3)
        for c in colls:
            print(f"    {kw}: {c['short_name']:12} {c['concept_id']} "
                  f"{c['start']}..{c['end'] or 'presente'}")

    cid = None
    colls = earthdata.search_collections(keyword="MOD11A2", page_size=10)
    for c in colls:
        # LP DAAC es el proveedor de referencia (los espejos INPE/FEDEO
        # devuelven 0 granules con bbox: verificado en la primera sonda).
        if c["concept_id"].endswith("-LPCLOUD"):
            cid = c["concept_id"]
            break
    print(f"    elegida: {cid}")

    t0 = time.perf_counter()
    granules = earthdata.search_granules(
        cid, bbox=(-117.2, 36.4, -117.0, 36.6),
        temporal="2024-07-01,2024-07-31", page_size=3)
    print(f"granules MOD11A2 DV jul-2024: {len(granules)} en {time.perf_counter()-t0:.1f}s")
    for g in granules:
        print(f"    {g['granule_id']} {g['size_mb']} MB {g['time_start'][:10]}")
        for u in g["download"]:
            print(f"      -> {u}")

    if granules and granules[0]["download"]:
        import requests
        url = granules[0]["download"][0]
        r = requests.head(url, timeout=60, allow_redirects=True)
        print(f"HEAD sin auth -> HTTP {r.status_code} "
              f"(401/403 = tras Earthdata Login; url-urs en el enlace)")
        if r.status_code in (401, 403):
            # earthaccess debería resolverlo con credenciales .env
            try:
                import earthaccess
                print("    earthaccess instalado:", earthaccess.__version__)
            except Exception as exc:
                print("    earthaccess:", exc)


if __name__ == "__main__":
    main()
