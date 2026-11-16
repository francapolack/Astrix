"""Ejemplo 3 — Buscar sitios candidatos en Marte.

Fuentes:
    a) USGS STAC      -> DTM de HiRISE y CTX (GeoTIFF de alta resolución)
    b) Mars Trek      -> capas WMTS del MOLA (relieve, pendiente, térmico)
    c) PDS Search API -> productos HiRISE/CTX por texto

Ejecuta:  python examples/03_marte_sitios.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from nsac.sources import pds, trek, usgs_stac

# Región de interés: cráter Jezero y alrededores (oeste, sur, este, norte)
BBOX = (77.2, 18.1, 77.8, 18.7)


def main() -> None:
    print("== a) DTMs de Marte en USGS STAC ==\n")
    presets = usgs_stac.dtm_presets()
    for nombre, coleccion in presets.items():
        if not nombre.startswith("marte"):
            continue
        items = usgs_stac.search([coleccion], bbox=BBOX, limit=3)
        print(f"{nombre:20} ({coleccion}) -> {len(items)} items en Jezero")
        for item in items:
            print(f"   - {item['id']}  {usgs_stac.best_asset(item)}")

    print("\n== b) Capas de Mars Trek ==\n")
    for capa in trek.find_layers("MOLA", "mars")[:6]:
        print(f"- {capa['id']:46} {capa['title']}")
    for capa in trek.find_layers("Thermal", "mars")[:6]:
        print(f"- {capa['id']:46} {capa['title']}")

    print("\n== c) Bundles y colecciones PDS (archivo planetario) ==\n")
    for bundle in pds.search_bundles("mro")[:3]:
        print(f"- {bundle['lidvid']}")
        print(f"  {bundle['title']}")
        for col in pds.bundle_collections(bundle["lidvid"])[:3]:
            print(f"     · {col['lidvid']}")


if __name__ == "__main__":
    main()
