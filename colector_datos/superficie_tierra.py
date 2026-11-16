"""superficie_tierra.py — reflectancia/albedo de la TIERRA con el mismo
formato que la superficie lunar (rama `tierra-datos-crudos`).

FUENTE (sin credenciales): Sentinel-2 L2A via Earth Search (STAC público de
Element84 sobre AWS; bucket 'sentinel-cogs' abierto, verificado con HEAD y
window read). Cada granule es un COG correcto (tileado): la lectura remota
/vsicurl de una ventana de ~1000x1100 px tarda ~13 s frío por banda (medido),
nada comparado con el tile completo (223 MB por banda).

QUÉ SE CALCULA (mismas claves que `superficie.py`):
  - 'reflectancia_albedo': reflectancia de superficie VISIBLE (media de las
    bandas B02 azul / B03 verde / B04 rojo, escala 0-1). Es el análogo de
    los canales solares 1-2 de Diviner (0.3-0.6 µm).
  - 'ndvi': (B08-B04)/(B08+B04) — para la Tierra este índice es el marcador
    de "seco/baldío vs vegetado", clave para un análogo marciano.
  - 'tipo_roca': heurística por umbral de brillo (equivalente documentado de
    la clasificación lunar; NO dice mineralogía, solo claridad del terreno).
  - 'minerales_predominantes' y 'materiales_y_polvo': notas honestas (la
    Tierra no tiene CRISM/Clementine; la geología local se confirma con el
    mapa geológico USGS o trabajo de campo).

MÁSCARA de nubes/agua con la banda SCL (Scene Classification Layer):
se descartan las clases 0-3 y 8-10 (sin dato/sombra/nubes/cirros) y la 6
(agua); se conservan 4 (vegetación), 5 (no vegetado), 7 y 11 (nieve).

CACHÉ: la búsqueda STAC pasa por cache_catalogo.json_o_red (igual que Treks)
y las ventanas de bandas se guardan como .npz en data/cache/s2/ (por
item+bbox, históricos como el resto del proyecto): segunda visita tibia.
"""

from __future__ import annotations

import warnings
import time
from pathlib import Path
from typing import Any

from . import topografia_dtm, utilidades

STAC_EARTH_SEARCH = "https://earth-search.aws.element84.com/v1/search"
COLECCION = "sentinel-2-l2a"
CARPETA_S2 = (Path("data") / "cache" / "s2")

# Bandas a leer por ventana (claves del asset STAC): azul, verde, rojo,
# infrarrojo cercano (NDVI) y la clasificación de escena.
BANDAS = ("blue", "green", "red", "nir", "scl")


def _escena(lat: float, lon: float, radio: float,
            nubes_max: float = 50.0) -> dict[str, Any] | None:
    """Última escena Sentinel-2 L2A que cubra la caja, con pocas nubes.

    Pasa por la caché de catálogos (misma pauta que Treks): para la demo
    la respuesta queda en disco y la consulta tibia no depende de AWS.
    Devuelve el dict STAC del item o None (sin cobertura/nubes).
    """
    import requests
    from . import cache_catalogo

    bbox = utilidades.caja_stac(lat, lon, radio)
    nombre = (f"earthsearch_s2_{lat:.2f}_{lon:.2f}_{radio:.2f}")

    def _productor():
        r = requests.post(
            STAC_EARTH_SEARCH,
            json={"bbox": list(bbox), "collections": [COLECCION], "limit": 10,
                  "query": {"eo:cloud_cover": {"lt": nubes_max}}},
            timeout=120)
        r.raise_for_status()
        feats = r.json().get("features", [])
        feats.sort(key=lambda f: f.get("properties", {}).get("datetime", ""),
                   reverse=True)
        return feats

    feats, _de_cache = cache_catalogo.json_o_red(nombre, _productor)
    return feats[0] if feats else None


def _leer_ventana(item: dict[str, Any], lat: float, lon: float,
                  radio: float, aviso=None) -> dict[str, Any]:
    """Window read remoto de las bandas del item, con caché npz local.

    Devuelve {banda: matriz float64 (reflectancia; SCL como uint8)} +
    metadatos del tile (CRS, transform). NUNCA lanza: los fallos van en
    'error' de la sección llamadora.
    """
    import numpy as np
    import rasterio
    import rasterio.warp
    from rasterio.windows import from_bounds

    CARPETA_S2.mkdir(parents=True, exist_ok=True)
    oeste, sur, este, norte = utilidades.caja_stac(lat, lon, radio)
    clave = (f"{item.get('id', 'item')}_{oeste:.4f}_{sur:.4f}"
             f"_{este:.4f}_{norte:.4f}").replace(".", "p")
    ruta_npz = CARPETA_S2 / f"{clave}.npz"
    if ruta_npz.exists():
        with np.load(ruta_npz, allow_pickle=True) as f:
            datos = {k: f[k] for k in f.files}
        return {"bandas": datos, "de_cache": True}

    bandas: dict[str, Any] = {}
    for b in BANDAS:
        url = (item.get("assets", {}).get(b) or {}).get("href")
        if not url:
            return {"bandas": {}, "error": f"el item no trae banda '{b}'"}
        if aviso:
            aviso(f"leyendo banda {b} (remoto, COG)...")
        t0 = time.perf_counter()
        with rasterio.open(f"/vsicurl/{url}") as src:
            xs, ys = rasterio.warp.transform(
                "EPSG:4326", src.crs, [oeste, este], [sur, norte])
            win = from_bounds(min(xs), min(ys), max(xs), max(ys),
                              transform=src.transform)
            arr = src.read(1, window=win)
            bandas["_crs"] = str(src.crs)
            bandas["_transform"] = np.asarray(src.transform)
        if b == "scl":
            bandas["scl"] = arr.astype("uint8")
            bandas["_scl_resolucion_m"] = 20.0  # SCL va a 20 m; las bandas, a 10
        else:
            # Reflectancia L2A: DN/10000; 0 = sin dato.
            z = arr.astype("float64") / 10000.0
            z[z == 0] = np.nan
            bandas[b] = z
        bandas[f"_{b}_s"] = round(time.perf_counter() - t0, 1)

    try:
        np.savez_compressed(ruta_npz,
                            **{k: v for k, v in bandas.items()
                               if not k.startswith("_") and not k.endswith("_s")})
    except Exception:
        pass  # sin caché: la consulta sigue siendo válida
    return {"bandas": bandas, "de_cache": False}


def _scl_a_escala(scl, forma: tuple[int, int]):
    """Lleva la máscara SCL (20 m) a la malla de las bandas (10 m).

    Sentinel-2 entrega la SCL a la mitad de resolución: cada píxel de SCL
    cubre 2x2 píxeles de las bandas. Repetimos cada píxel 2x2 (vecino más
    próximo, sin interpolar clases) y recortamos/empadronamos con NaN
    fuera (banda y máscara vienen de ventanas que pueden diferir 1 px).
    """
    import numpy as np

    up = np.repeat(np.repeat(scl, 2, axis=0), 2, axis=1)
    f = min(up.shape[0], forma[0])
    c = min(up.shape[1], forma[1])
    out = np.full(forma, 255, dtype=up.dtype)  # 255 = fuera (no existe en SCL)
    out[:f, :c] = up[:f, :c]
    return out


def datos_superficie_tierra(lat: float, lon: float, radio: float,
                            aviso=None) -> dict[str, Any]:
    """Superficie terrestre con las mismas claves que `superficie.py`."""
    import numpy as np

    def _aviso(msg: str) -> None:
        if aviso:
            aviso(msg)

    seccion: dict[str, Any] = {
        "fuente": "Sentinel-2 L2A (Earth Search/Element84, COG en AWS abierto)",
    }
    try:
        escena = _escena(lat, lon, radio)
        if escena is None:
            seccion["nota"] = ("sin escena Sentinel-2 con pocas nubes que "
                               "cubra esta caja en los últimos días")
            return seccion
        props = escena.get("properties", {})
        seccion["escena"] = {
            "id": escena.get("id"),
            "fecha": (props.get("datetime") or "")[:10],
            "nubes_pct": props.get("eo:cloud_cover"),
            "tile_mgrs": props.get("grid:code"),
        }

        lectura = _leer_ventana(escena, lat, lon, radio, aviso=aviso)
        b = lectura["bandas"]
        if not b or "red" not in b:
            seccion["error"] = lectura.get("error", "no se pudieron leer las bandas")
            return seccion

        # Máscara de nubes/agua/sombra con SCL, llevada a la malla de 10 m
        # (la SCL va a 20 m: 1 píxel suyo cubre 2x2 de las bandas).
        scl = b.get("scl")
        rojo = b["red"]
        if scl is None:
            land = np.ones_like(rojo, dtype=bool)
        else:
            land = np.isin(_scl_a_escala(scl, rojo.shape), (4, 5, 7, 11))
        for banda in ("blue", "green", "red", "nir"):
            if banda in b:
                b[banda] = np.where(land, b[banda], np.nan)

        visible = None
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")  # píxeles 100% NaN: esperable
            visible = np.nanmean([b["blue"], b["green"], b["red"]], axis=0)
        vals = visible[np.isfinite(visible)]
        if vals.size < 100:
            seccion["nota"] = ("casi todos los píxeles quedaron enmascarados "
                               "(nubes o agua): la reflectancia describe muy "
                               "poca superficie")
        refl = topografia_dtm._a_estadisticas(
            vals.size, float(vals.min()), float(vals.mean()),
            float(np.median(vals)), float(vals.max()), float(vals.std()))
        refl["nota"] = ("reflectancia de superficie visible (media de "
                        "B02 azul/B03 verde/B04 rojo, escala 0-1): el "
                        "análogo de los canales solares de Diviner")
        seccion["reflectancia_albedo"] = refl
        seccion["n_pixeles"] = int(vals.size)
        seccion["nubes_en_caja_pct"] = round(
            100.0 * float((~land).sum()) / max(land.size, 1), 1)

        # NDVI (seco/baldío vs vegetado) — indicador clave de análogo marciano.
        nir, red = b.get("nir"), b["red"]
        if nir is not None:
            with np.errstate(invalid="ignore", divide="ignore"):
                ndvi = (nir - red) / (nir + red)
            ndv = ndvi[np.isfinite(ndvi)]
            if ndv.size >= 100:
                st = topografia_dtm._a_estadisticas(
                    ndv.size, float(ndv.min()), float(ndv.mean()),
                    float(np.median(ndv)), float(ndv.max()), float(ndv.std()))
                st["nota"] = ("(NIR-Rojo)/(NIR+Rojo): ~0 o negativo = "
                              "terreno baldío (análogo marciano); "
                              "positivo alto = vegetación")
                seccion["ndvi"] = st

        # Heurística de brillo (equivalente terrestre de la clasificación
        # lunar; NO es mineralogía).
        media = (seccion["reflectancia_albedo"] or {}).get("media")
        if isinstance(media, (int, float)):
            if media > 0.28:
                clase = ("superficie clara — salares/roca expuesta/arena "
                         "clara (alto albedo)")
            elif media < 0.13:
                clase = ("superficie oscura — roca basáltica/lava o suelo "
                         "húmedo (bajo albedo)")
            else:
                clase = "superficie intermedia — mixta"
            seccion["tipo_roca"] = {
                "clasificacion": clase,
                "metodo": ("umbral sobre la reflectancia visible media de "
                           "Sentinel-2 (heurística; confírmalo con geología "
                           "local o el mapa geológico USGS)"),
            }

        seccion["minerales_predominantes"] = {
            "nota": ("la Tierra no tiene CRISM/Clementine: la composición "
                     "se confirma con geología local; el NDVI de arriba "
                     "separa baldío de vegetado"),
        }
        seccion["materiales_y_polvo"] = {
            "nota": ("para el análogo, el 'polvo' terrestre relevante son "
                     "las tormentas de arena: MODIS aerosol (CMR) o Sentinel-5P "
                     "lo cuantifican; consulta futura opcional"),
        }
        seccion["tiempos_s"] = {
            k: b.get(f"_{k}_s") for k in BANDAS if f"_{k}_s" in b}
        seccion["de_cache"] = lectura.get("de_cache", False)
    except Exception as exc:
        seccion["error"] = str(exc)
    return seccion
