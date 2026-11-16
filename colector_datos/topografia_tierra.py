"""topografia_tierra.py — topografía de la TIERRA con el mismo formato que
Luna y Marte (rama `tierra-datos-crudos`).

Es el paso 1 de la ruta de acción para cerrar la brecha de la Tierra:
`obtener_datos_sitio('tierra', ...)` hoy solo trae catálogos; este módulo
trae NÚMEROS crudos de elevación/pendiente/rugosidad/cráteres con las MISMAS
claves y definiciones que `topografia_dtm.analizar_sitio` (Kaguya/CTX).

FUENTE: Copernicus DEM GLO-30 (ESA), tiles GeoTIFF de 1°x1° a 1 arcseg
(~30 m/px) en el bucket público de AWS. Sin autenticación, sin STAC y sin
ninguna llamada de catálogo: el nombre del tile es DETERMINISTA a partir
del bbox (sondeado y verificado contra la red real, ver
`sonda_glo30.py` / NOTAS). Convención real del bucket:
    Copernicus_DSM_COG_10_S25_00_W070_00_DEM/Copernicus_DSM_COG_10_S25_00_W070_00_DEM.tif
(lat 2 dígitos, lon SIEMPRE 3 dígitos: W070, no W70; etiqueta por floor()
del grado entero que contiene el sitio).

CRS: EPSG:4326 estándar (la Tierra es el único cuerpo donde PROJ funciona
sin trucos). Alturas relativas al geoide EGM2008.

VENTAJA vs la vía Kaguya/CTX: el tile cubre 1°x1° completo, así que una
caja de hasta ±0.5° (el tope RADIO_MAX_GRADOS) SIEMPRE cabe en UN tile y
la cobertura es del 100 % — salvo en el antimeridiano, que se parte en dos
ventanas como hace `utilidades.cajas_gds`.

MODOS (idéntico a `topografia_dtm.analizar_sitio`):
  'descargar' (por defecto): baja el tile COMPLETO (30-50 MB) a
    data/cache/dtm/ y las visitas siguientes leen del disco en <0.5 s.
  'remoto': /vsicurl lee solo la ventana por HTTP. Consume menos disco
    pero el tile es band-strided (no COG en teselas): una ventana pequeña
    son cientos de peticiones de rango (medido: ~22 s una de 360x360).
MIDAS reales (nov 2026, red lenta ~0.2-0.4 MB/s): remoto 22 s frío;
descarga 196 s frío / 0.07 s tibio; GLO-90 (4.5 MB) baja en 11 s — ver
sub-rama `tierra-glo90-rapida` para la comparativa.
"""

from __future__ import annotations

import math
import time
from pathlib import Path
from typing import Any

from . import constantes, topografia_dtm

# Radio del datum terrestre (esferoide WGS84, semieje mayor) para convertir
# grados de píxel en metros. En la Tierra no se NECESITA para la CRS (PROJ
# la resuelve), pero las métricas usan la misma aproximación de arco que
# los otros cuerpos: 1° de latitud ≈ 111.32 km.
RADIO_DATUM_TIERRA_M = 6378137.0

# El bucket público de AWS (sin credenciales, sin requester-pays; verificado
# con HEAD y con listado S3). GLO-90 existe con el mismo esquema pero otro
# prefijo de nombre ('COG_30' en vez de 'COG_10') y resolución de 90 m.
BASE_GLO30 = "https://copernicus-dem-30m.s3.amazonaws.com"


def tile_name(lat: float, lon: float) -> str:
    """Nombre del tile GLO-30 de 1°x1° que contiene (lat, lon).

    Convención verificada contra el bucket real: etiqueta por el grado
    ENTERO que contiene el sitio (floor), latitud con 2 dígitos y
    longitud con 3 (W070_00, E014_00...). N/S y E/W según el signo.
    """
    f0 = math.floor(lat)
    f1 = math.floor(lon)
    lat_s = f"{abs(f0):02d}_00"
    lon_s = f"{abs(f1):03d}_00"
    return ("Copernicus_DSM_COG_10_"
            + ("N" if f0 >= 0 else "S") + lat_s
            + "_" + ("E" if f1 >= 0 else "W") + lon_s + "_DEM")


def url_tile(lat: float, lon: float, resolucion: str = "30m") -> str:
    """URL pública del TIFF del tile que contiene el sitio."""
    t = tile_name(lat, lon)
    if resolucion == "30m":
        return f"{BASE_GLO30}/{t}/{t}.tif"
    # GLO-90: mismo esquema, prefijo COG_30 (número interno del producto)
    t90 = t.replace("COG_10", "COG_30")
    return (f"https://copernicus-dem-90m.s3.amazonaws.com/{t90}/{t90}.tif")


def analizar_sitio(lat: float, lon: float, radio: float,
                   modo_tile: str = "descargar", aviso=None,
                   resolucion: str = "30m") -> dict[str, Any]:
    """Topografía terrestre de UN sitio, mismo formato que la vía DTM lunar.

    resolucion: '30m' (GLO-30, ~30 m/px, tile de 30-50 MB) o '90m'
      (GLO-90, tile de ~4-5 MB: la descarga en frío es ~10x más rápida, a
      cambio de menos detalle en pendiente/rugosidad). La comparativa
      medida vive en `prueba_tierra_glo90.py` y en NOTAS_NOCTURNAS.md.

    Devuelve (NUNCA lanza; los fallos van en 'error'):
      fuente, via='glo30', elevacion/pendiente/rugosidad (formato
      n/min/max/media/mediana/desv_estandar de `utilidades.estadisticas`),
      crateres (heurística de malla, idéntica a la de Kaguya/CTX),
      resolucion_m, cobertura_fraccion, pixeles_validos_fraccion, confiable
      y los tiempos stac_s (=0, no hay catálogo)/descarga_s/computo_s/total_s.
    """
    import numpy as np

    def _aviso(msg: str) -> None:
        if aviso:
            aviso(msg)

    out: dict[str, Any] = {
        "fuente": (f"Copernicus DEM GLO-{resolucion[:-1]} "
                   "(AWS público) vía rasterio"),
        "cuerpo": "earth",
        "resolucion": resolucion,
    }
    try:
        # --- caja (puede cruzar el antimeridiano: se parte como el GDS) ---
        oeste = ((lon - radio) + 180.0) % 360.0 - 180.0
        este = ((lon + radio) + 180.0) % 360.0 - 180.0
        sur = max(-90.0, lat - radio)
        norte = min(90.0, lat + radio)
        cruza_anti = oeste > este
        # El tile se elige por el CENTRO (una caja ≤ ±0.5° cabe en 1-2 tiles
        # solo si pisa el borde; el mosaico multi-tile queda pendiente, como
        # en la vía lunar, y se reporta con cobertura < 1).
        out["stac_s"] = 0.0   # sin catálogo: el nombre del tile es determinista
        tile_id = tile_name(lat, lon)
        if resolucion == "90m":
            # Prefijo/nombre real del bucket GLO-90 (COG_30) + sufijo de
            # caché para NO confundir tiles de 30 y de 90 m en disco.
            tile_id = tile_id.replace("COG_10", "COG_30") + "_90m"
        out["tile"] = tile_id
        url = url_tile(lat, lon, resolucion)
        out["url"] = url

        # --- descarga (con reutilización local, igual que la vía lunar) ---
        CARPETA_TILES = topografia_dtm.CARPETA_TILES
        CARPETA_TILES.mkdir(parents=True, exist_ok=True)
        ruta_tif = CARPETA_TILES / f"{tile_id}.tif"
        if modo_tile == "remoto":
            ruta_tif = f"/vsicurl/{url}"
            out["descarga_s"] = 0.0
            out["de_cache"] = False
            out["acceso"] = "remoto (vsicurl)"
        elif ruta_tif.exists():
            _aviso(f"tile ya en disco: {ruta_tif.name}")
            out["descarga_s"] = 0.0
            out["de_cache"] = True
        else:
            from nsac import http
            _aviso(f"bajando tile GLO-{resolucion[:-1]} ({tile_id})...")
            t0 = time.perf_counter()
            try:
                http.download(url, ruta_tif)
            except Exception as exc:
                # Los tiles de OCÉANO PURO ni siquiera existen en el
                # bucket (404 verificado: el bucket no incluye tiles
                # completamente marinos). Mensaje claro en vez del 404.
                if "404" in str(exc):
                    out["error"] = (
                        f"sin tile GLO-{resolucion[:-1]} para {tile_id}: no "
                        "existe en el bucket (típico de un sitio en mar "
                        "abierto)")
                else:
                    out["error"] = f"descarga falló: {exc}"
                return out
            out["descarga_s"] = round(time.perf_counter() - t0, 1)
            out["de_cache"] = False

        # --- window read + métricas (misma receta que la vía lunar) -------
        import rasterio
        from rasterio.windows import from_bounds

        t0 = time.perf_counter()
        with rasterio.open(ruta_tif) as src:
            # Caja en grados -> lon/lat del raster (EPSG:4326: identidad;
            # en la Tierra PROJ no da problemas, a diferencia de la Luna).
            izq, der = oeste, este
            abajo, arriba = sur, norte
            if cruza_anti:
                # El antimeridiano divide la caja: la ventana del tile
                # cubre solo un lado; el otro lado queda fuera y lo
                # reporta la cobertura (como en los polos de la Luna).
                if oeste < 0:  # p.ej. lon 179.9: el trozo oeste (179.x..180)
                    der = 180.0
                else:          # p.ej. lon -179.9: el trozo este (-180..-179.x)
                    izq = -180.0

            b = src.bounds
            ancho_caja = der - izq
            alto_caja = arriba - abajo
            inter_x = max(0.0, min(der, b.right) - max(izq, b.left))
            inter_y = max(0.0, min(arriba, b.top) - max(abajo, b.bottom))
            out["cobertura_fraccion"] = round(
                (inter_x * inter_y) / max(ancho_caja * alto_caja, 1e-12), 3)

            win = from_bounds(max(izq, b.left), max(abajo, b.bottom),
                              min(der, b.right), min(arriba, b.top),
                              transform=src.transform)
            fila0, col0 = int(win.row_off), int(win.col_off)
            z = src.read(1, window=win).astype("float64")
            z_transform = src.transform
            crs = src.crs
            nodata = src.nodata

        if nodata is not None:
            z[z == nodata] = np.nan
        z[z < -1e5] = np.nan
        # Océano: GLO-30 pone altura 0.0 (no nodata) sobre el mar. Un tile
        # marino se comprime a unos KB y sus métricas serían "0 m y llano":
        # se detecta y se avisa, para no confundir con un desierto llano.
        validos = int(np.isfinite(z).sum())
        if validos < 25:
            out["error"] = "el trozo leído casi no tiene píxeles válidos"
            return out
        out["pixeles_validos_fraccion"] = round(validos / max(z.size, 1), 3)
        out["confiable"] = out["pixeles_validos_fraccion"] >= 0.5

        media = float(np.nanmean(z))
        if media == 0.0 and float(np.nanstd(z)) == 0.0:
            out["nota_oceano"] = ("el tile leído parece océano (altura 0 en "
                                  "todos los píxeles): las métricas no "
                                  "describen terreno terrestre")

        dx_m, dy_m = topografia_dtm._metros_por_pixel(
            z_transform, crs, lat, RADIO_DATUM_TIERRA_M)
        out["resolucion_m"] = round((dx_m + dy_m) / 2.0, 1)
        out["datum_elevacion"] = "EGM2008 (Copernicus GLO-30)"

        out["elevacion"] = topografia_dtm._a_estadisticas(
            validos, np.nanmin(z), media, float(np.nanmedian(z)),
            float(np.nanmax(z)), float(np.nanstd(z)))
        out["elevacion"]["n_pixeles"] = validos

        gy, gx = np.gradient(z, dy_m, dx_m)
        pend = np.degrees(np.arctan(np.hypot(gx, gy)))
        pend = pend[np.isfinite(pend) & np.isfinite(z)]
        out["pendiente"] = topografia_dtm._a_estadisticas(
            pend.size, pend.min(), float(pend.mean()), float(np.median(pend)),
            float(pend.max()), float(pend.std()))
        out["pendiente"]["n_pixeles"] = int(pend.size)

        # Rugosidad: celdas de ~100 m. OJO: si el DEM es más grueso que la
        # celda (GLO-90: ~89 m/px), una celda de 100 m contiene 1 píxel y su
        # std es 0 (rugosidad falsa "lisa"): mínimo 2 píxeles por lado y el
        # tamaño real queda reportado en tamano_celda_m.
        paso_r = max(2, int(round(100.0 / max(dx_m, 1e-6))))
        h = (z.shape[0] // paso_r) * paso_r
        w = (z.shape[1] // paso_r) * paso_r
        if h >= paso_r and w >= paso_r:
            import warnings
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                bloques = z[:h, :w].reshape(h // paso_r, paso_r,
                                            w // paso_r, paso_r)
                rug_celda = np.nanstd(bloques, axis=(1, 3))
            rug = rug_celda[np.isfinite(rug_celda)]
            if rug.size:
                out["rugosidad"] = topografia_dtm._a_estadisticas(
                    rug.size, rug.min(), float(rug.mean()),
                    float(np.median(rug)), float(rug.max()), float(rug.std()))
                out["rugosidad"]["n_celdas_100m"] = int(rug.size)
                out["rugosidad"]["tamano_celda_m"] = round(paso_r * dx_m, 1)
            else:
                out["rugosidad"] = {"nota": "sin celdas con datos suficientes"}
        else:
            out["rugosidad"] = {"nota": "caja más pequeña que una celda de 100 m"}

        out["crateres"] = topografia_dtm._crateres_de_malla(
            z, z_transform, fila0, col0, crs, dx_m, RADIO_DATUM_TIERRA_M)

        out["computo_s"] = round(time.perf_counter() - t0, 1)
        out["total_s"] = round(
            out["stac_s"] + out["descarga_s"] + out["computo_s"], 1)
    except ImportError as exc:
        out["error"] = (f"dependencia ausente ({exc}): instala rasterio")
    except Exception as exc:
        out["error"] = str(exc)
    return out
