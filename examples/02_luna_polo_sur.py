"""Ejemplo 2 — Caracterizar un sitio del polo sur lunar con datos reales.

Combina tres fuentes que sí dan datos crudos:

    a) Diviner (GDS REST)  -> temperatura de superficie por punto
    b) LOLA    (GDS REST)  -> elevación por punto
    c) USGS STAC           -> DTM de alta resolución del polo sur (Kaguya TC)
    d) Moon Trek           -> capas ya renderizadas (PSR, pendiente, rugosidad)

Ejecuta:  python examples/02_luna_polo_sur.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import json

import pandas as pd

from nsac.sources import pds, trek, usgs_stac

# Caja alrededor de Shackleton (polo sur). minlat, maxlat, oeste, este.
# Ojo: el GDS rechaza cajas que cruzan el meridiano 0 ("Invalid Lat/Lon
# Bounding Box"), así que ésta va de 0 a 0.1 E y es pequeña a propósito.
BBOX = (-89.95, -89.85, 0.0, 0.1)
# USGS STAC (y casi todos los STAC) usan (oeste, sur, este, norte)
BBOX_STAC = (0.0, -89.95, 0.1, -89.85)


def main() -> None:
    print("== a) Temperatura superficial (Diviner RDR vía GDS) ==\n")
    # canales 3-9 = térmicos; los 1-2 son solares y no dan temperatura
    df_div = pds.gds_extract_points("divinerrdr", BBOX, channel="ffttttttt")
    print(f"puntos: {len(df_div)}  columnas: {list(df_div.columns)[:12]}")

    if "tb" in df_div.columns:
        tb = pd.to_numeric(df_div["tb"], errors="coerce")
        validos = tb[(tb > 20) & (tb < 400)]  # fuera de rango = canal solar o píxel malo
        print(
            f"tb (K): validos={len(validos)}/{len(tb)} "
            f"min={validos.min():.1f}  media={validos.mean():.1f}  max={validos.max():.1f}  "
            f"<110 K: {(validos < 110).mean() * 100:.1f}%"
        )
        Path("data").mkdir(exist_ok=True)
        df_div.to_csv("data/diviner_shackleton.csv", index=False)
        print("-> data/diviner_shackleton.csv")

    print("\n== b) Elevación (LOLA RDR vía GDS) ==\n")
    df_lola = pds.gds_extract_points("lolardr", BBOX)
    print(f"puntos: {len(df_lola)}")
    geo = ["D1_Latitude", "D1_Longitude", "D1_Radius"]
    if all(c in df_lola.columns for c in geo):
        lola = df_lola[geo].apply(pd.to_numeric, errors="coerce")
        lola = lola[lola["D1_Radius"] > 0]  # -99 = disparo sin eco
        print(lola.describe().round(3).to_string())

    print("\n== c) DTM de alta resolución (USGS STAC) ==\n")
    dtm = usgs_stac.search(
        [usgs_stac.dtm_presets()["luna_polo_sur"]],
        bbox=BBOX_STAC,
        limit=5,
    )
    for item in dtm:
        print(f"- {item['id']}")
        print(f"    {usgs_stac.best_asset(item)}")

    print("\n== d) Capas listas para el mapa (Moon Trek) ==\n")
    for capa in trek.find_layers("PSR", "moon"):
        print(f"- {capa['id']:42} {capa['title']}")
    for capa in trek.find_layers("Slope", "moon")[:5]:
        print(f"- {capa['id']:42} {capa['title']}")

    print("\n== e) Metadatos de productos LRO/LOLA por bbox (ODE REST) ==\n")
    res = pds.ode_products("LRO", "LOLA", "RDR4", bbox=BBOX, limit=2)
    print(json.dumps(res, indent=2)[:800])


if __name__ == "__main__":
    main()
