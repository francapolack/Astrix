"""Ejemplo 4 — Radar de apertura sintética (SAR) como criterio de rugosidad.

Dos vías:
    a) CSA datos abiertos RCM  -> GeoTIFF HH/HV de escenas concretas (descarga directa)
    b) ASF                     -> búsqueda de escenas Sentinel-1 / RADARSAT-2

La textura SAR distingue superficies lisas (hielo, salares) de roca suelta,
que es justo uno de los criterios de un análogo lunar o marciano.

Ejecuta:  python examples/04_sar_rcm.py            (solo lista)
          python examples/04_sar_rcm.py --download (baja la primera escena)
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from nsac.sources import asf, csa


def main() -> None:
    bajar = "--download" in sys.argv

    print("== a) Regiones del dataset abierto RCM ==\n")
    regiones = csa.rcm_regions()
    print(", ".join(regiones))

    region = "Canadian Arctic"
    print(f"\n== b) Escenas RCM en '{region}' ==\n")
    escenas = csa.rcm_scenes(region)
    for e in escenas[:5]:
        print(f"- {e['scene']}  {e['date']}  {e['polarization']}  {e['product']}")

    if escenas:
        print("\n== c) Archivos de la primera escena ==\n")
        archivos = csa.rcm_scene_files(escenas[0]["url"])
        for f in archivos:
            print(f"- {f['folder'] or '/':10} {f['name']}")

        if bajar:
            print("\nDescargando GeoTIFF (pueden ser varios cientos de MB)...")
            rutas = csa.rcm_download(escenas[0]["url"], dest="data/rcm")
            for r in rutas:
                print(f"-> {r}")

    print("\n== d) Búsqueda SAR en ASF (Sentinel-1) ==\n")
    # ASF usa (sur, oeste, norte, este)
    for g in asf.search(platform="Sentinel-1", bbox=(-25.5, -70.5, -23.0, -68.5), max_results=3):
        print(f"- {g['granule']}  {g['start']}  {g['size_mb']} MB")

    print("\n== e) Catálogo EODMS (RCM y RADARSAT-1 abiertos) ==\n")
    for c in csa.eodms_collections():
        print(f"- {c['id']:24} {c['title']}")


if __name__ == "__main__":
    main()
