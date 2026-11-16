"""NASA Solar System Treks: teselas WMTS ya renderizadas de Luna y Marte.

Es la vía más rápida para poner un mapa bonito en la app: LOLA DEM, pendiente,
rugosidad, iluminación, regiones en sombra permanente (PSR) y mosaicos NAC.

- Catálogo de capas: Solr público por cuerpo (moon, mars, mercury, ...)
- Teselas: WMTS REST, con tres proyecciones (EQ, NP, SP = polos).
"""

from __future__ import annotations

import re
from typing import Any

from ..http import get, get_json

BASES = {
    "moon": "https://trek.nasa.gov/moon",
    "mars": "https://trek.nasa.gov/mars",
    "mercury": "https://trek.nasa.gov/mercury",
    "titan": "https://trek.nasa.gov/titan",
    "vesta": "https://trek.nasa.gov/vesta",
    "ceres": "https://trek.nasa.gov/ceres",
}

_PROJ_CODE = {"EQ": "eq", "NP": "np", "SP": "sp"}

_SEARCH_TMPL = (
    "{base}/TrekServices/ws/index/{projtype}/searchItems"
    "?start=0&rows={rows}"
    "&facetKeys=itemType%7CproductCat2%7CserviceTypes%7CthumbnailURLDir"
    "&facetValues=product%7C-%28DEM%20ConfidenceRaw%20Slope%29%7CMosaic%7C%5B%2A%20TO%20%2A%5D"
)


def layers(body: str = "moon", projtype: str = "polar", rows: int = 5000) -> list[dict[str, Any]]:
    """Catálogo de capas publicadas para un cuerpo.

    projtype: 'polar' (polos) o 'eq' (equirectangular, vista global).
    """
    base = BASES[body.lower()]
    url = _SEARCH_TMPL.format(base=base, projtype=projtype, rows=rows)
    docs = get_json(url)["response"]["docs"]
    out = []
    for d in docs:
        out.append(
            {
                "id": d.get("productLabel"),
                "title": d.get("title"),
                "mission": d.get("mission"),
                "instrument": d.get("instrument"),
                "resolution": d.get("resolution"),
                "bbox": d.get("bbox"),
                "uuid": d.get("item_UUID"),
                "projection": d.get("trekProjection"),
            }
        )
    return out


def find_layers(keyword: str, body: str = "moon", projtype: str = "polar") -> list[dict[str, Any]]:
    kw = keyword.lower()
    return [
        l
        for l in layers(body=body, projtype=projtype)
        if kw in (l["id"] or "").lower() or kw in (l["title"] or "").lower()
    ]


def layer_services(body: str, uuid: str) -> list[dict[str, Any]]:
    """Endpoints WMTS (uno por tipo de servicio) de una capa."""
    base = BASES[body.lower()]
    data = get_json(f"{base}/TrekServices/ws/index/getLayerServices", params={"uuid": uuid})
    return data["response"]["docs"]


def tile_template(body: str, product_label: str, endpoint: str | None = None) -> dict[str, Any]:
    """Lee el GetCapabilities de la capa y devuelve plantilla y extensión de tesela.

    Devuelve dict con 'endpoint', 'tile_matrix_set', 'ext' y 'url_template'
    (con {z}/{row}/{col} listos para usar).
    """
    base = BASES[body.lower()]
    endpoint = endpoint or _endpoint_for(body, product_label)
    caps_url = f"{endpoint}/1.0.0/WMTSCapabilities.xml"
    xml = get(caps_url).text
    tms = re.search(r"<TileMatrixSet>([^<]+)</TileMatrixSet>", xml).group(1)
    template = re.search(r'template="([^"]+)"', xml).group(1)
    ext = template.rsplit(".", 1)[-1]
    url_template = f"{endpoint}/1.0.0/default/{tms}/{{z}}/{{row}}/{{col}}.{ext}"
    return {
        "endpoint": endpoint,
        "tile_matrix_set": tms,
        "ext": ext,
        "url_template": url_template,
        "capabilities": caps_url,
    }


def _endpoint_for(body: str, product_label: str) -> str:
    for l in layers(body=body):
        if l["id"] == product_label:
            services = layer_services(body, l["uuid"])
            if services:
                return services[0]["endPoint"]
    raise KeyError(f"No encontré la capa {product_label} en {body}; usa find_layers()")


def tile_url(body: str, product_label: str, z: int, row: int, col: int, endpoint: str | None = None) -> str:
    t = tile_template(body, product_label, endpoint)
    return t["url_template"].format(z=z, row=row, col=col)


def leaflet_layer(body: str, product_label: str) -> dict[str, str]:
    """Config lista para L.tileLayer en Leaflet (usar con CRS simple L.CRS.EPSG3857
    sólo si tu visor reinterpreta las proyecciones polares; para mapas planetarios
    conviene Leaflet con CRS personalizado o MapLibre con proyección IAU)."""
    t = tile_template(body, product_label)
    return {
        "url": t["url_template"].replace("{z}", "{z}").replace("{row}", "{y}").replace("{col}", "{x}"),
        "tile_matrix_set": t["tile_matrix_set"],
        "attribution": "NASA/JPL Solar System Treks",
    }
