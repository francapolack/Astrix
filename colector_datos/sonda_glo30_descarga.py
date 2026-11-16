"""Sonda 3: descargar tile GLO-30 completo vs lectura remota vs lectura local.

Mide tres caminos para el mismo dato (Atacama ±0.05°):
  A) ventana remota /vsicurl (ya medida en sonda_glo30: lenta)
  B) descarga completa del tile (37-42 MB) a la caché + window read local
  C) ventana local (tile ya en disco) - el camino tibio

Además calcula pendiente/rugosidad/cráteres con la MISMA receta que
topografia_dtm (gradiente + celdas de 100 m) para validar el formato.
"""

import time
from pathlib import Path

import numpy as np
import rasterio
from rasterio.windows import from_bounds

from .sonda_glo30 import url_tile

CARPETA = Path("data/cache/dtm")
CARPETA.mkdir(parents=True, exist_ok=True)


def medir(lat, lon, radio, etiqueta):
    from nsac import http
    t = url_tile(lat, lon)
    nombre = t.rsplit("/", 1)[-1]
    ruta = CARPETA / nombre

    t0 = time.perf_counter()
    if not ruta.exists():
        print(f"  [{etiqueta}] descargando {nombre} (~40 MB)...")
        http.download(t, ruta)
        desc = time.perf_counter() - t0
        print(f"  [{etiqueta}] descarga: {desc:.1f}s")
    else:
        print(f"  [{etiqueta}] tile ya en caché ({ruta.stat().st_size/1e6:.0f} MB)")
    t_abre = time.perf_counter()
    with rasterio.open(ruta) as src:
        izq, sur, der, norte = lon - radio, lat - radio, lon + radio, lat + radio
        win = from_bounds(izq, sur, der, norte, transform=src.transform)
        z = src.read(1, window=win).astype("float64")
        print(f"  [{etiqueta}] abrir+window read local: "
              f"{time.perf_counter() - t_abre:.3f}s, ventana {z.shape}")
    return z


def metricas(z, lat, radio):
    dy = dx = (np.pi / 180.0) * 6378137.0 / (1 / 3600)  # 1 arcsec en metros (aprox WGS84)
    # Exacto: 1 arcsec vertical = 30.92 m; horizontal *= cos(lat)
    arc = np.pi * 6378137.0 / 180.0 / 3600.0
    dy_m = arc
    dx_m = arc * np.cos(np.radians(lat))
    z[z < -1e5] = np.nan
    n_valid = int(np.isfinite(z).sum())
    print(f"  píxeles válidos: {n_valid}/{z.size} "
          f"({100*n_valid/z.size:.0f}%), resolución {dx_m:.1f}/{dy_m:.1f} m/px")
    gy, gx = np.gradient(z, dy_m, dx_m)
    pend = np.degrees(np.arctan(np.hypot(gx, gy)))
    pend = pend[np.isfinite(pend) & np.isfinite(z)]
    paso_r = max(1, int(round(100.0 / max(dx_m, 1e-6))))
    h = (z.shape[0] // paso_r) * paso_r
    w = (z.shape[1] // paso_r) * paso_r
    import warnings
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        bloques = z[:h, :w].reshape(h // paso_r, paso_r, w // paso_r, paso_r)
        rug = np.nanstd(bloques, axis=(1, 3))
    rug = rug[np.isfinite(rug)]
    print(f"  elevación media {np.nanmean(z):.1f} m (std {np.nanstd(z):.1f})")
    print(f"  pendiente media {pend.mean():.3f}° máx {pend.max():.1f}° "
          f"(n={pend.size})")
    print(f"  rugosidad media {rug.mean():.2f} m mediana {np.median(rug):.2f} "
          f"(celdas {paso_r*dx_m:.0f} m, n={rug.size})")


if __name__ == "__main__":
    print("=== Atacama (-24.08, -69.47) ±0.05 ===")
    z = medir(-24.08, -69.47, 0.05, "A/B frío")
    metricas(z, -24.08, 0.05)
    z = medir(-24.08, -69.47, 0.05, "C tibio")
    metricas(z, -24.08, 0.05)
    print("=== Death Valley (36.5, -117.1) ±0.1 ===")
    z = medir(36.5, -117.1, 0.1, "DV")
    metricas(z, 36.5, 0.1)
    print("=== Atacama ±0.5 (caja grande, sin mosaico) ===")
    z = medir(-24.08, -69.47, 0.5, "grande")
    metricas(z, -24.08, 0.5)
