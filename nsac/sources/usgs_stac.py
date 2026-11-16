"""STAC de USGS Astrogeology: la mejor puerta para Luna y Marte.

Colecciones incluidas (18): LOLA, Kaguya Terrain Camera (DTM global y polos),
MRO HiRISE y CTX (DTM + observaciones), THEMIS, Galileo, Voyager.

Los assets son GeoTIFF/COG y COPC-LAZ públicos en S3.
"""

from __future__ import annotations

from typing import Any

from ..http import get_json, post_json

STAC = "https://stac.astrogeology.usgs.gov/api"


def collections() -> list[dict[str, Any]]:
    data = get_json(f"{STAC}/collections")
    return [
        {
            "id": c["id"],
            "title": c.get("title"),
            "description": (c.get("description") or "")[:160],
            "bbox": c.get("extent", {}).get("spatial", {}).get("bbox"),
        }
        for c in data["collections"]
    ]


def search(
    collection_ids: list[str] | None = None,
    bbox: tuple[float, float, float, float] | None = None,
    datetime_range: str | None = None,
    limit: int = 20,
    query: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Búsqueda STAC (POST /search).

    bbox = (oeste, sur, este, norte) en el cuerpo planetario correspondiente.
    Devuelve items simplificados con sus assets (GeoTIFF/COG, thumbnails).
    """
    payload: dict[str, Any] = {"limit": limit}
    if collection_ids:
        payload["collections"] = collection_ids
    if bbox:
        payload["bbox"] = list(bbox)
    if datetime_range:
        payload["datetime"] = datetime_range
    if query:
        payload["query"] = query
    data = post_json(f"{STAC}/search", payload)
    return [_simplify(f) for f in data.get("features", [])]


def _simplify(feature: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": feature.get("id"),
        "bbox": feature.get("bbox"),
        "datetime": (feature.get("properties") or {}).get("datetime"),
        "assets": {k: v.get("href") for k, v in (feature.get("assets") or {}).items()},
        "properties": feature.get("properties"),
    }


# Cada colección nombra sus assets de forma distinta.
_ASSET_PRIORITY = ("dtm", "data", "cog", "image", "orthoimage", "hillshade", "ortho_0")


def best_asset(item: dict[str, Any], prefer: tuple[str, ...] = _ASSET_PRIORITY) -> str | None:
    """Elige el asset raster/3D más útil de un item STAC.

    HiRISE/CTX exponen 'dtm' o 'image'; LOLA usa 'data' (COPC-LAZ); THEMIS 'image'.
    """
    for clave in prefer:
        if item["assets"].get(clave):
            return item["assets"][clave]
    for href in item["assets"].values():
        if isinstance(href, str) and href.lower().endswith((".tif", ".tiff", ".laz", ".copc.laz")):
            return href
    return None


def dtm_presets() -> dict[str, str]:
    """Colecciones más útiles para elegir sitios de aterrizaje/base."""
    return {
        "luna_polo_sur": "kaguya_terrain_camera_usgs_dtms_v2_southpolar",
        "luna_polo_norte": "kaguya_terrain_camera_usgs_dtms_v2_northpolar",
        "luna_global_dtm": "kaguya_terrain_camera_usgs_dtms_v2",
        "luna_puntos_lola": "lunar_orbiter_laser_altimeter",
        "marte_ctx_dtm": "mro_ctx_controlled_usgs_dtms",
        "marte_hirise_dtm": "mro_hirise_socet_dtms",
        "marte_themis": "mo_themis_controlled_mosaics",
    }
