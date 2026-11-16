"""NASA Earthdata: catálogo CMR (búsqueda) y mosaicos GIBS (teselas/ráster).

- CMR: https://cmr.earthdata.nasa.gov/search  (sin autenticación, solo Earth)
- GIBS: https://gibs.earthdata.nasa.gov       (Worldview sirve exactamente estas teselas)
- Descarga de granules: requiere Earthdata Login -> usar `earthaccess`.

Ojo: CMR es SOLO datos de la Tierra. Para Luna/Marte usa nsac.sources.pds,
usgs_stac o trek.
"""

from __future__ import annotations

from typing import Any
from xml.etree import ElementTree as ET

from ..http import get, get_json

CMR = "https://cmr.earthdata.nasa.gov/search"
GIBS_CAPS = "https://gibs.earthdata.nasa.gov/wmts/epsg3857/best/1.0.0/WMTSCapabilities.xml"


def search_collections(
    keyword: str | None = None,
    provider: str | None = None,
    page_size: int = 20,
    page_num: int = 1,
) -> list[dict[str, Any]]:
    """Busca datasets en CMR por texto libre (p.ej. 'SMAP soil moisture')."""
    params: dict[str, Any] = {"page_size": page_size, "page_num": page_num}
    if keyword:
        params["keyword"] = keyword
    if provider:
        params["provider"] = provider
    data = get_json(f"{CMR}/collections.json", params=params)
    out = []
    for e in data.get("feed", {}).get("entry", []):
        out.append(
            {
                "concept_id": e.get("id"),
                "short_name": e.get("short_name"),
                "title": (e.get("title") or "").strip(),
                "provider": e.get("data_center"),
                "bbox": (e.get("boxes") or [None])[0],
                "start": (e.get("time_start") or "")[:10],
                "end": (e.get("time_end") or "")[:10],
            }
        )
    return out


def search_granules(
    concept_id: str,
    bbox: tuple[float, float, float, float] | None = None,
    temporal: str | None = None,
    page_size: int = 50,
) -> list[dict[str, Any]]:
    """Busca granules (archivos) de una colección. bbox = (oeste, sur, este, norte)."""
    params: dict[str, Any] = {"concept_id": concept_id, "page_size": page_size}
    if bbox:
        params["bounding_box"] = ",".join(str(v) for v in bbox)
    if temporal:
        params["temporal"] = temporal
    data = get_json(f"{CMR}/granules.json", params=params)
    out = []
    for g in data.get("feed", {}).get("entry", []):
        links = [l.get("href") for l in g.get("links", []) if l.get("rel", "").endswith("/data#") or l.get("title") == "Download"]
        out.append(
            {
                "granule_id": g.get("id"),
                "title": g.get("title"),
                "time_start": g.get("time_start"),
                "time_end": g.get("time_end"),
                "size_mb": round(float(g.get("granule_size") or 0) / 1e6, 2)
                if g.get("granule_size") else None,
                "download": links[:1],
            }
        )
    return out


# ---------------------------------------------------------------- GIBS teselas
_gibs_layers: list[dict[str, str]] | None = None


def gibs_layers() -> list[dict[str, str]]:
    """Lista de capas disponibles en GIBS (EPSG:3857), cacheada en memoria."""
    global _gibs_layers
    if _gibs_layers is None:
        root = ET.fromstring(get(GIBS_CAPS).content)
        ns = {"wmts": "http://www.opengis.net/wmts/1.0", "ows": "http://www.opengis.net/ows/1.1"}
        layers = []
        for layer in root.findall(".//wmts:Layer", ns):
            ident = layer.findtext("ows:Identifier", default="", namespaces=ns)
            title = layer.findtext("ows:Title", default="", namespaces=ns)
            fmt = layer.findtext("wmts:Format", default="image/jpeg", namespaces=ns)
            tms = layer.findtext("wmts:TileMatrixSetLink/wmts:TileMatrixSet", default="", namespaces=ns)
            layers.append({"id": ident, "title": title, "format": fmt, "matrix_set": tms})
        _gibs_layers = layers
    return _gibs_layers


def search_gibs_layers(keyword: str) -> list[dict[str, str]]:
    """Filtra capas GIBS por palabra clave ('true color', 'land surface temperature'...)."""
    kw = keyword.lower()
    return [l for l in gibs_layers() if kw in l["id"].lower() or kw in l["title"].lower()]


def gibs_tile_url(
    layer: str,
    date: str = "default",
    z: int = 2,
    x: int = 1,
    y: int = 1,
    ext: str = "jpg",
) -> str:
    """URL de una tesela XYZ (Leaflet/MapLibre) del mosaico GIBS.

    `date` en formato YYYY-MM-DD para capas diarias, o 'default' para estáticas.
    """
    return (
        "https://gibs.earthdata.nasa.gov/wmts/epsg3857/best/"
        f"{layer}/default/{date}/GoogleMapsCompatible_Level9/{z}/{y}/{x}.{ext}"
    )


def gibs_kvp_url(layer: str, date: str = "default", **params: Any) -> str:
    """Alternativa KVP de GIBS (útil para WMS/WMTS no-REST)."""
    base = "https://gibs.earthdata.nasa.gov/wmts/epsg3857/best/wmts.cgi"
    query = {"layer": layer, "tilematrixset": "GoogleMapsCompatible_Level9", "time": date, **params}
    return base + "?" + "&".join(f"{k}={v}" for k, v in query.items())
