"""Ejemplo 1 — Buscar y caracterizar análogos terrestres con datos de la Tierra.

Flujo del reto: un sitio análogo debe compartir con la Luna/Marte topografía,
geología, ambiente y recursos. Aquí se monta el pipeline mínimo:

    1. catálogo de variables en NASA CMR (qué dataset usar para cada criterio)
    2. teselas GIBS listas para el mapa (Worldview = mismas capas)
    3. tabla de sitios candidatos con sus URLs de teselas y de búsqueda

Ejecuta:  python examples/01_analogos_tierra.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import json

from nsac.sources import earthdata

# Sitios análogos clásicos (los que menciona el enunciado y otros útiles)
SITIOS = {
    "Atacama (Chile)": {"bbox": (-70.5, -25.5, -68.5, -23.0), "análogo_de": "Marte: desierto hiperárido"},
    "Haughton (Canadá)": {"bbox": (-90.8, 75.3, -89.2, 75.5), "análogo_de": "Marte: cráter de impacto"},
    "Death Valley (EEUU)": {"bbox": (-117.4, 36.2, -116.6, 36.7), "análogo_de": "Marte/Luna: desierto y salares"},
    "Valles Marineris análogo (Río Tinto)": {"bbox": (-6.7, 37.6, -6.4, 37.8), "análogo_de": "Marte: mineralogía ácida"},
    "Dry Valleys (Antártida)": {"bbox": (161.0, -78.0, 164.0, -77.0), "análogo_de": "Marte/Luna: frío extremo"},
    "Tenerife (Teide)": {"bbox": (-16.8, 28.1, -16.4, 28.4), "análogo_de": "Luna: volcánico y tubos de lava"},
    "Mono Lake (EEUU)": {"bbox": (-119.2, 37.9, -118.8, 38.1), "análogo_de": "Marte: carbonatos y arsénico"},
}

# Variable -> (búsqueda en CMR, por qué sirve)
VARIABLES = {
    "temperatura_superficie": ("MODIS land surface temperature", "gradiente térmico día/noche"),
    "humedad_suelo": ("SMAP soil moisture", "disponibilidad de agua/regolito"),
    "reflectancia": ("MODIS surface reflectance", "albedo y mineralogía"),
    "elevacion": ("SRTM elevation", "topografía y pendientes"),
    "vegetacion": ("MODIS NDVI", "contraste con superficie estéril"),
}


def main() -> None:
    print("== 1. Catálogo de variables (NASA CMR) ==\n")
    catalogo = {}
    for nombre, (query, motivo) in VARIABLES.items():
        colecciones = earthdata.search_collections(query, page_size=3)
        catalogo[nombre] = {"motivo": motivo, "colecciones": colecciones}
        print(f"{nombre:24} {motivo}")
        for c in colecciones[:2]:
            print(f"   - {c['concept_id']}  {c['title'][:70]}")

    print("\n== 2. Teselas GIBS para el visor (sin API key) ==\n")
    import math

    capa_lst = "MODIS_Terra_Land_Surface_Temp_Day"
    z = 5  # vista regional
    teselas = {}
    for sitio, meta in SITIOS.items():
        w, s, e, n = meta["bbox"]
        lat_rad = math.radians((s + n) / 2)
        n_tiles = 2**z
        x = int((w + e + 360) / 2 / 360 * n_tiles)
        y = int((1 - math.log(math.tan(lat_rad) + 1 / math.cos(lat_rad)) / math.pi) / 2 * n_tiles)
        teselas[sitio] = earthdata.gibs_tile_url(capa_lst, date="2024-06-15", z=z, x=x, y=y)
        print(f"{sitio:38} {teselas[sitio]}")

    print("\n== 3. Guardando resumen ==\n")
    out = Path("data")
    out.mkdir(exist_ok=True)
    destino = out / "analogos_tierra.json"
    destino.write_text(
        json.dumps(
            {"sitios": SITIOS, "variables": catalogo, "teselas_gibs": teselas},
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    print(f"-> {destino}")


if __name__ == "__main__":
    main()
