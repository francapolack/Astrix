"""Copernicus Data Space Ecosystem (CDSE).

- STAC (búsqueda): https://catalogue.dataspace.copernicus.eu/stac  (abierto)
- OData (listado/descarga): https://catalogue.dataspace.copernicus.eu/odata/v1
- Descarga: requiere cuenta gratuita -> token OAuth2 (flujo password).
"""

from __future__ import annotations

import os
from typing import Any

from ..http import download, get_json, post_json

STAC = "https://catalogue.dataspace.copernicus.eu/stac"
ODATA = "https://catalogue.dataspace.copernicus.eu/odata/v1"
TOKEN = "https://identity.dataspace.copernicus.eu/auth/realms/CDSE/protocol/openid-connect/token"
DOWNLOAD = "https://download.dataspace.copernicus.eu/odata/v1/Products({pid})/$value"


def search_stac(
    collections: list[str],
    bbox: tuple[float, float, float, float] | None = None,
    datetime_range: str | None = None,
    limit: int = 20,
    query: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Búsqueda STAC. Colecciones: sentinel-2-l1c, sentinel-1-grd, sentinel-3-..."""
    payload: dict[str, Any] = {"collections": collections, "limit": limit}
    if bbox:
        payload["bbox"] = list(bbox)
    if datetime_range:
        payload["datetime"] = datetime_range
    if query:
        payload["query"] = query
    data = post_json(f"{STAC}/search", payload)
    return [
        {
            "id": f.get("id"),
            "collection": f.get("collection"),
            "datetime": (f.get("properties") or {}).get("datetime"),
            "cloud_cover": (f.get("properties") or {}).get("eo:cloud_cover"),
            "bbox": f.get("bbox"),
            "assets": {k: v.get("href") for k, v in (f.get("assets") or {}).items()},
        }
        for f in data.get("features", [])
    ]


def odata_products(
    collection: str = "SENTINEL-2",
    bbox: tuple[float, float, float, float] | None = None,
    top: int = 20,
    extra_filter: str | None = None,
) -> list[dict[str, Any]]:
    """Listado OData (más clásico que STAC). bbox = (oeste, sur, este, norte)."""
    filters = [f"Collection/Name eq '{collection}'"]
    if bbox:
        w, s, e, n = bbox
        filters.append(
            "OData.CSC.Intersects(area=geography'SRID=4326;POLYGON(("
            f"{w} {s},{e} {s},{e} {n},{w} {n},{w} {s}))')"
        )
    if extra_filter:
        filters.append(extra_filter)
    data = get_json(
        f"{ODATA}/Products",
        params={"$filter": " and ".join(filters), "$top": top, "$orderby": "ContentDate/Start desc"},
    )
    return [
        {
            "id": p.get("Id"),
            "name": p.get("Name"),
            "content_length": p.get("ContentLength"),
            "start": (p.get("ContentDate") or {}).get("Start"),
            "s3": (p.get("S3Path") or None),
        }
        for p in data.get("value", [])
    ]


def get_token(username: str | None = None, password: str | None = None) -> str:
    """Token OAuth2 para descargar (cuenta gratuita de CDSE)."""
    username = username or os.getenv("CDSE_USERNAME")
    password = password or os.getenv("CDSE_PASSWORD")
    if not username or not password:
        raise RuntimeError("Faltan CDSE_USERNAME / CDSE_PASSWORD (ver .env.example)")
    resp = post_json(
        TOKEN,
        data={"grant_type": "password", "username": username, "password": password, "client_id": "cdse-public"},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    return resp["access_token"]


def download_product(product_id: str, token: str, dest: str | None = None):
    """Descarga un producto por UUID (el token caduca ~10 min)."""
    url = DOWNLOAD.format(pid=product_id)
    return download(url, dest, headers={"Authorization": f"Bearer {token}"})
