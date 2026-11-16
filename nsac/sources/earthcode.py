"""ESA Open Science Data Catalogue (EarthCODE).

Portal: https://opensciencedata.esa.int
API STAC: https://eoapi.workspace.earthcode.eox.at/stac

Contiene productos y "experiments" de proyectos ESA (biomasa, océano, hielo,
atmósfera...). Muy útil para variables ambientales de sitios análogos
(temperatura, viento, albedo, humedad).
"""

from __future__ import annotations

from typing import Any

from ..http import get_json, post_json

API = "https://eoapi.workspace.earthcode.eox.at/stac"


def collections(limit: int = 100) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    url = f"{API}/collections"
    params: dict[str, Any] = {"limit": limit}
    while url:
        data = get_json(url, params=params)
        out += [
            {
                "id": c["id"],
                "title": c.get("title"),
                "description": (c.get("description") or "")[:160],
            }
            for c in data.get("collections", [])
        ]
        nxt = next((l for l in data.get("links", []) if l.get("rel") == "next"), None)
        url, params = (nxt["href"], None) if nxt else ("", None)
    return out


def search(
    collection_ids: list[str] | None = None,
    bbox: tuple[float, float, float, float] | None = None,
    datetime_range: str | None = None,
    limit: int = 20,
) -> list[dict[str, Any]]:
    payload: dict[str, Any] = {"limit": limit}
    if collection_ids:
        payload["collections"] = collection_ids
    if bbox:
        payload["bbox"] = list(bbox)
    if datetime_range:
        payload["datetime"] = datetime_range
    data = post_json(f"{API}/search", payload)
    return [
        {
            "id": f.get("id"),
            "collection": f.get("collection"),
            "bbox": f.get("bbox"),
            "datetime": (f.get("properties") or {}).get("datetime"),
            "assets": {k: v.get("href") for k, v in (f.get("assets") or {}).items()},
        }
        for f in data.get("features", [])
    ]
