"""Sonda de variantes de nombre de tile GLO-30 (halla la convención real)."""

import requests

SITIOS = [
    (-24.08, -69.47, "Atacama"),
    (-20.5, -69.8, "Salar Grande"),
    (66.0, -61.0, "Haughton"),
]
BASE = "https://copernicus-dem-30m.s3.amazonaws.com/"


def _prueba(lat_ent, lon_ent, tipo):
    """Genera el nombre con floor o round y devuelve la URL."""
    if tipo == "floor":
        f0, f1 = math.floor(lat_ent), math.floor(lon_ent)
    else:  # 'ceil-neg' = ceil para negativos
        f0 = math.ceil(lat_ent) if lat_ent < 0 else math.floor(lat_ent)
        f1 = math.ceil(lon_ent) if lon_ent < 0 else math.floor(lon_ent)
    lat_s = f"{abs(f0):02d}_00"
    lon_s = f"{abs(f1):03d}_00" if abs(f1) >= 100 else f"{abs(f1):02d}_00"
    n = ("Copernicus_DSM_COG_10_" + ("N" if f0 >= 0 else "S") + lat_s
         + "_" + ("E" if f1 >= 0 else "W") + lon_s + "_DEM")
    return n, BASE + n + "/" + n + ".tif"


import math

print("=== Variantes por sitio ===")
for lat, lon, sitio in SITIOS:
    for tipo in ("floor", "ceil-neg"):
        nombre, url = _prueba(lat, lon, tipo)
        r = requests.head(url, timeout=30)
        marca = "OK " if r.status_code == 200 else f"{r.status_code}"
        print(f"  {sitio} [{tipo}] {nombre} -> {marca}")

print("=== Listado del bucket (prefix Atacama) ===")
r = requests.get(BASE, params={"list-type": "2", "prefix": "Copernicus_DSM_COG_10_S25", "max-keys": "20"}, timeout=30)
print("HTTP", r.status_code)
if r.ok:
    print(r.text[:1500])
