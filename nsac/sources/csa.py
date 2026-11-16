"""CSA (Agencia Espacial Canadiense): RADARSAT / RCM.

Tres accesos distintos, todos sin coste:

1. Portal CKAN de datos abiertos (metadata de los datasets).
   https://donnees-data.asc-csa.gc.ca/api/3/action/package_search
2. Datos abiertos RCM: árbol HTTP de escenas (GeoTIFF HH/HV + manifest.safe).
   https://donnees-data.asc-csa.gc.ca/users/OpenData_DonneesOuvertes/pub/RCM/
3. EODMS (NRCan): catálogo/ordenación de RADARSAT-2 y RCM vía RAPI.
   https://www.eodms-sgdot.nrcan-rncan.gc.ca/wes/rapi/

El árbol RCM está organizado por región: Antarctica, Canadian Arctic, ...
"""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import quote
from xml.etree import ElementTree as ET

from ..http import download, get, get_json

CKAN = "https://donnees-data.asc-csa.gc.ca/api/3/action"
RCM_ROOT = "https://donnees-data.asc-csa.gc.ca/users/OpenData_DonneesOuvertes/pub/RCM/"
EODMS = "https://www.eodms-sgdot.nrcan-rncan.gc.ca/wes/rapi"

_LINK_RE = re.compile(r'<a href="([^"?#][^"]*)">([^<]+)</a>', re.I)


def _dir_links(url: str) -> list[tuple[str, str]]:
    """Pares (href, nombre) de un índice Apache, sin enlaces de navegación."""
    html = get(url).text
    out = []
    for href, name in _LINK_RE.findall(html):
        name = name.strip()
        if not name or name.startswith("[") or href.startswith("/"):
            continue
        out.append((href, name))
    return out


# ------------------------------------------------------------------ CKAN
def ckan_search(query: str = "RCM", rows: int = 10) -> list[dict[str, Any]]:
    data = get_json(f"{CKAN}/package_search", params={"q": query, "rows": rows})
    out = []
    for p in data["result"]["results"]:
        out.append(
            {
                "name": p.get("name"),
                "title": p.get("title"),
                "notes": (p.get("notes") or "")[:300],
                "resources": [
                    {"format": r.get("format"), "name": r.get("name"), "url": r.get("url")}
                    for r in p.get("resources", [])
                ],
            }
        )
    return out


def ckan_package(name: str = "rcm") -> dict[str, Any]:
    return get_json(f"{CKAN}/package_show", params={"id": name})["result"]


# -------------------------------------------------------- árbol RCM (escenas)
def rcm_regions() -> list[str]:
    """Regiones del dataset abierto (Antarctica, Canadian Arctic, ...)."""
    return [name.strip("/") for href, name in _dir_links(RCM_ROOT) if href.endswith("/")]


def rcm_scenes(region: str) -> list[dict[str, Any]]:
    """Escenas de una región, con metadatos extraídos del nombre.

    Nombre típico: RCM2_OK1050583_PK1050584_1_SCLND_20191105_135220_HH_HV_GRD
    """
    url = RCM_ROOT + quote(region) + "/"
    out = []
    for href, name in _dir_links(url):
        if not href.endswith("/"):
            continue
        scene = name.strip("/")
        tokens = scene.split("_")
        fecha = re.search(r"_(\d{8})_(\d{6})_", scene)
        pol = re.search(r"_((?:HH|HV|VV|VH)(?:_(?:HH|HV|VV|VH))?)_", scene)
        out.append(
            {
                "scene": scene,
                "url": url + href,
                "satellite": tokens[0] if tokens else None,
                "beam_mode": tokens[4] if len(tokens) > 4 else None,
                "date": fecha.group(1) if fecha else None,
                "time": fecha.group(2) if fecha else None,
                "polarization": (pol.group(1) or "").replace("_", "+") if pol else None,
                "product": tokens[-1] if tokens else None,
            }
        )
    return out


def rcm_scene_files(scene_url: str) -> list[dict[str, Any]]:
    """Archivos de una escena: imagery/*.tif, manifest.safe, license.pdf..."""
    files: list[dict[str, Any]] = []
    for href, name in _dir_links(scene_url):
        if href.endswith("/"):
            sub = scene_url + quote(name.strip("/")) + "/"
            for h2, n2 in _dir_links(sub):
                if not h2.endswith("/"):
                    files.append({"name": n2, "url": sub + h2, "folder": name.strip("/")})
        else:
            files.append({"name": name, "url": scene_url + href, "folder": ""})
    return files


def rcm_download(scene_url: str, pattern: str = r"\.tif$", dest: str | None = None):
    """Descarga los GeoTIFF de una escena (por defecto todos los .tif)."""
    files = [f for f in rcm_scene_files(scene_url) if re.search(pattern, f["name"], re.I)]
    if not files:
        raise FileNotFoundError("La escena no tiene archivos que casen con el patrón")
    return [download(f["url"], dest) for f in files]


# --------------------------------------------------------------------- EODMS
def eodms_collections() -> list[dict[str, Any]]:
    """Catálogo de colecciones de EODMS (RADARSAT-2, RCM, ...)."""
    xml = get(f"{EODMS}/collections", headers={"Accept": "application/xml"}).content
    root = ET.fromstring(xml)
    out = []
    for col in root.iter():
        if col.tag.rsplit("}", 1)[-1] != "collection":
            continue
        out.append({"id": col.get("collectionId"), "title": col.get("title")})
    return out
