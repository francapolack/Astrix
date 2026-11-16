"""sonda_glo30.py — Sonda del Paso 1 (rama `tierra-datos-crudos`).

Comprueba que el DEM Copernicus GLO-30 es accesible SIN autenticación en el
bucket público de AWS, y que el nombre de tile es determinista a partir del
bbox (tiles de 1°x1°, p.ej. Copernicus_DSM_COG_10_S25_00_W70_00_DEM).

Además mide la lectura de una ventana con /vsicurl (sin descargar el tile)
y la comparación contra la descarga del tile completo.

Ejecutar desde la raíz:  python -m colector_datos.sonda_glo30
"""

import math
import time


def tile_name(lat: float, lon: float) -> str:
    """Nombre del tile GLO-30 de 1°x1° que contiene (lat, lon).

    Convención verificada: floor() de la latitud/longitud y etiqueta
    N/S + EE_00 / E/W + EEE_00 (abs con ceros a la izquierda).
    """
    f0 = math.floor(lat)
    f1 = math.floor(lon)
    lat_s = f"{abs(f0):02d}_00"
    # Convención REAL del bucket (hallada sondeando): la longitud SIEMPRE
    # lleva 3 dígitos (p.ej. E014_00, W070_00); la latitud, 2 (N36_00).
    lon_s = f"{abs(f1):03d}_00"
    return ("Copernicus_DSM_COG_10_"
            + ("N" if f0 >= 0 else "S") + lat_s
            + "_" + ("E" if f1 >= 0 else "W") + lon_s + "_DEM")


def url_tile(lat: float, lon: float) -> str:
    t = tile_name(lat, lon)
    return f"https://copernicus-dem-30m.s3.amazonaws.com/{t}/{t}.tif"


def sondear() -> None:
    import requests

    sitios = [
        (-24.08, -69.47, "Atacama"),
        (36.5, -117.1, "Death Valley"),
        (-20.5, -69.8, "Salar Grande"),
        (66.0, -61.0, "Haughton (Ártico)"),
        (-89.9, 0.05, "polo -89.9 (¿existe tile?)"),
    ]
    print("=== Sonda 1: HEAD sin auth al bucket público ===")
    for lat, lon, sitio in sitios:
        url = url_tile(lat, lon)
        t0 = time.perf_counter()
        try:
            r = requests.head(url, timeout=30)
            tam = r.headers.get("Content-Length", "?")
            print(f"  {sitio}: {tile_name(lat, lon)} -> HTTP {r.status_code} "
                  f"tam={tam} en {time.perf_counter() - t0:.2f}s")
        except Exception as exc:
            print(f"  {sitio}: FALLO {exc}")

    print("=== Sonda 2: window read remoto (/vsicurl) Atacama ±0.05° ===")
    import numpy as np
    import rasterio
    from rasterio.windows import from_bounds

    lat, lon, radio = -24.08, -69.47, 0.05
    t0 = time.perf_counter()
    ruta = f"/vsicurl/{url_tile(lat, lon)}"
    with rasterio.open(ruta) as src:
        meta = {"crs": str(src.crs), "resolucion": src.res,
                "bounds": src.bounds, "nodata": src.nodata,
                "tam": src.width, "alto": src.height}
        izq, der, sur, norte = lon - radio, lon + radio, lat - radio, lat + radio
        win = from_bounds(izq, sur, der, norte, transform=src.transform)
        t_lect = time.perf_counter() - t0
        z = src.read(1, window=win).astype("float64")
        t_total = time.perf_counter() - t0
    print(f"  meta: {meta}")
    z[z < -1e5] = np.nan
    print(f"  ventana {z.shape}, abierta+leída en {t_lect:.2f}/{t_total:.2f}s")
    print(f"  elevación: media {np.nanmean(z):.1f} min {np.nanmin(z):.1f} "
          f"max {np.nanmax(z):.1f}")


if __name__ == "__main__":
    sondear()
