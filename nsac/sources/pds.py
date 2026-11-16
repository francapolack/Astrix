"""Planetary Data System (PDS): las cuatro vías reales de acceso.

1. PDS Search API  -> catálogo global PDS4 (búsqueda por texto o campos PDS4).
2. Listados HTTP   -> descarga directa de productos en pds-geosciences.wustl.edu.
3. ODE REST        -> metadatos de productos LRO/MRO/... por bbox y fecha.
4. GDS REST        -> extracción de DATOS (LOLA, Diviner) por bbox, ya empaquetados
                      en CSV/TAB. Es la vía más rápida para empezar a analizar.
"""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import urljoin

from ..http import download, get, get_json

PDS_SEARCH = "https://pds.nasa.gov/api/search/1"
ODE = "https://oderest.rsl.wustl.edu/live2"
GDS = "https://oderest.rsl.wustl.edu/livegds"
PDS_GEO = "https://pds-geosciences.wustl.edu"


# ------------------------------------------------------------------ 1. catálogo
def _docs(params: dict[str, Any]) -> list[dict[str, Any]]:
    """Normaliza los documentos que devuelve el registro PDS."""
    data = get_json(f"{PDS_SEARCH}/products", params=params)
    out = []
    for doc in data.get("data", []):
        props = doc.get("properties") or {}
        out.append(
            {
                "lidvid": doc.get("id"),
                "title": doc.get("title"),
                "product_class": doc.get("type"),
                "node": (props.get("ops:Harvest_Info.ops:node_name") or [None])[0],
                "description": (doc.get("title") or "")[:200],
                "label_url": (props.get("ops:Label_File_Info.ops:file_ref") or [None])[0],
            }
        )
    return out


def search_bundles(keyword: str | None = None) -> list[dict[str, Any]]:
    """Bundles PDS4 (un bundle = un dataset completo, p.ej. 'lro-l-lroc-2-edr').

    El parámetro `keywords` del API no filtra de forma fiable, así que se piden
    todos los bundles (~900) y se filtra en local. Es rápido y determinista.
    """
    bundles = _docs({"q": 'product_class eq "Product_Bundle"', "limit": 1000})
    if not keyword:
        return bundles
    kw = keyword.lower()
    return [b for b in bundles if kw in (b["lidvid"] or "").lower() or kw in (b["title"] or "").lower()]


def search_collections(keyword: str | None = None, limit: int = 500) -> list[dict[str, Any]]:
    """Colecciones PDS4 (un nivel por debajo del bundle: EDR, RDR, documentos...).

    Ojo: el API no deja filtrar por texto en servidor, así que se bajan `limit`
    colecciones y se filtran en local. Para ir a lo seguro usa
    `bundle_collections(lidvid)` sobre un bundle concreto.
    """
    cols = _docs({"q": 'product_class eq "Product_Collection"', "limit": limit})
    if not keyword:
        return cols
    kw = keyword.lower()
    return [c for c in cols if kw in (c["lidvid"] or "").lower() or kw in (c["title"] or "").lower()]


def search_products(q: str | None = None, limit: int = 25) -> dict[str, Any]:
    """Consulta avanzada con sintaxis PDS4.

    q: 'product_class eq "Product_Bundle"'
       'pds:Primary_Result_Summary.pds:processing_level eq "Raw"'
    """
    params: dict[str, Any] = {"limit": limit}
    if q:
        params["q"] = q
    data = get_json(f"{PDS_SEARCH}/products", params=params)
    return {"hits": data.get("summary", {}).get("hits"), "products": _docs(params)}


def members(lidvid: str, limit: int = 100) -> list[dict[str, Any]]:
    """Hijos de un bundle/colección (browse jerárquico del archivo).

    `members` de un bundle   -> sus colecciones.
    `members` de una colección -> sus productos observacionales.
    """
    data = get_json(f"{PDS_SEARCH}/products/{lidvid}/members", params={"limit": limit})
    return [
        {"lidvid": doc.get("id"), "title": doc.get("title"), "product_class": doc.get("type")}
        for doc in data.get("data", [])
    ]


def bundle_collections(bundle_lidvid: str) -> list[dict[str, Any]]:
    """Colecciones de un bundle concreto (rápido y exacto)."""
    return members(bundle_lidvid)


def search_properties() -> list[dict[str, str]]:
    """Lista de campos indexados disponibles para `q` (para autocompletar filtros)."""
    return get_json(f"{PDS_SEARCH}/properties")


# ------------------------------------------------------------- 2. listado HTTP
_LINK_RE = re.compile(r'<a href="([^"?][^"]*)">([^<]+)</a>', re.I)


def list_dir(url: str, files_only: bool = False) -> list[dict[str, Any]]:
    """Lee un listado Apache de PDS Geosciences (o cualquier índice similar).

    Devuelve nombre, url absoluta y si es directorio.
    """
    html = get(url).text
    entries = []
    for href, text in _LINK_RE.findall(html):
        text = text.strip()
        if not text or text.startswith("[") or href.startswith("#"):
            continue
        is_dir = href.endswith("/")
        if files_only and is_dir:
            continue
        entries.append(
            {
                "name": text.rstrip("/"),
                "url": urljoin(url, href),
                "is_dir": is_dir,
            }
        )
    return entries


def latest_rdr_dir() -> str:
    """Directorio del release más reciente de Diviner RDR que exista en el nodo."""
    return f"{PDS_GEO}/lro/lro-l-dlre-4-rdr-v1/lrodlr_1002/data/"


# ---------------------------------------------------------------- 3. ODE REST
def ode_iipt() -> list[dict[str, Any]]:
    """Combinaciones válidas (target, host, instrumento, tipo de producto).

    Imprescindible: ODE rechaza combinaciones que no existan, p.ej. LRO/LOLA/RDR
    no existe; el válido es LRO/LOLA/RDR4.
    """
    data = get_json(ODE, params={"query": "iipt", "output": "JSON"})
    return data["ODEResults"]["IIPTSets"]["IIPTSet"]


def ode_products(
    ihid: str,
    iid: str,
    pt: str,
    target: str = "moon",
    bbox: tuple[float, float, float, float] | None = None,
    limit: int = 50,
) -> dict[str, Any]:
    """Productos con metadatos (huella, centro, URL de datos).

    bbox = (minlat, maxlat, oeste, este). Ejemplo Luna: LRO / LOLA / RDR4.
    """
    params: dict[str, Any] = {
        "query": "products",
        "target": target,
        "ihid": ihid,
        "iid": iid,
        "pt": pt,
        "results": "cm",
        "output": "JSON",
        "limit": limit,
    }
    if bbox:
        minlat, maxlat, western, eastern = bbox
        params.update(
            {"minlat": minlat, "maxlat": maxlat, "westernlon": western, "easternlon": eastern, "loc": "b"}
        )
    data = get_json(ODE, params=params)["ODEResults"]
    products = data.get("Products", {}).get("Product", [])
    if isinstance(products, dict):
        products = [products]
    return {
        "count": int(data.get("Count", 0)),
        "error": data.get("Error"),
        "products": [
            {
                # 'Id' existe en los productos PDS3 pero es None en los PDS4
                # (p.ej. THEMIS IRBTR4): en esos casos el identificador se
                # extrae de la URL de ficheros (product_id=i98521009btr).
                "id": p.get("Id") or _id_de_url(p.get("FilesURL")),
                # 'Start_time' es PDS3; los PDS4 traen Observation_time (el
                # punto medio entre inicio y fin de la observación) y
                # Solar_time (hora local solar: util para día/noche).
                "start_time": p.get("Start_time") or p.get("Observation_time"),
                "observation_time": p.get("Observation_time"),
                "solar_time": p.get("Solar_time"),
                "center_lat": p.get("Center_latitude"),
                "center_lon": p.get("Center_longitude"),
                "data_url": p.get("External_url") or p.get("Data_url"),
                "files_url": p.get("FilesURL"),
                "footprint": p.get("Footprint_C0_geometry"),
            }
            for p in products
        ],
    }


def _id_de_url(url: str | None) -> str | None:
    """product_id de una URL de ficheros de ODE (p.ej. i98521009btr)."""
    if not url:
        return None
    import re
    m = re.search(r"product_id=([A-Za-z0-9_]+)", url)
    return m.group(1) if m else None


# ----------------------------------------------------------------- 4. GDS REST
GDS_PRESETS = {
    # query        : (descripción, parámetros extra útiles)
    "lolardr": ("LRO LOLA altimetría puntual (lat, lon, radio)", {}),
    "divinerrdr": (
        "LRO Diviner temperatura de superficie por canal",
        # 9 banderas, una por canal: 1-2 son solares (no dan temperatura) y
        # 3-9 son térmicos (7.55-200 µm). Con "tffffffff" sólo llega el canal
        # solar y la columna tb no tiene sentido físico.
        {"channel": "ffttttttt"},
    ),
}


def gds_query(
    query: str,
    bbox: tuple[float, float, float, float],
    results: str = "vsi",
    fmt: str = "JSON",
    **extra: Any,
) -> dict[str, Any]:
    """Lanza una consulta granular por bbox y devuelve los archivos generados.

    bbox = (minlat, maxlat, oeste, este)
    results: v=valores, s=estadísticas, i=imagen -> 'vsi' trae todo.

    Ojo: el GDS rechaza cajas que cruzan el meridiano 0 (p.ej. -0.5 a 0.5);
    parte la consulta en dos o usa longitudes 0-360.
    """
    minlat, maxlat, western, eastern = bbox
    params: dict[str, Any] = {
        "query": query,
        "results": results,
        "output": fmt,
        "minlat": minlat,
        "maxlat": maxlat,
        "westernlon": western,
        "easternlon": eastern,
        **GDS_PRESETS.get(query, ("", {}))[1],
        **extra,
    }
    raw = get_json(GDS, params=params, timeout=300)  # GDS puede tardar minutos
    body = raw["GDSResults"]
    # El GDS, cuando falla o no encuentra nada, responde con 'ResultFiles'
    # como STRING (p.ej. 'No results found...'), no como objeto/ausente:
    # detectarlo y convertirlo en error claro (y no un 'str' object has no
    # attribute get' críptico río abajo).
    resultado_archivos = body.get("ResultFiles", {})
    if isinstance(resultado_archivos, str):
        raise RuntimeError(
            "GDS sin archivos de resultados para esta consulta "
            f"(respuesta del servidor: {resultado_archivos[:200]!r})")
    files = resultado_archivos.get("ResultFile", [])
    if isinstance(files, dict):
        files = [files]
    return {
        "count": int(body.get("Count", 0)),
        "note": body.get("StateSummary", {}).get("StatusNote"),
        "state": body.get("StateSummary"),
        "error": body.get("Error"),
        "files": [{"url": f["URL"], "size_kb": f.get("SizeKB")} for f in files],
    }


def gds_extract_points(
    query: str,
    bbox: tuple[float, float, float, float],
    dest: str | None = None,
    **extra: Any,
):
    """Consulta GDS y devuelve un DataFrame con los puntos.

    Para Diviner las columnas incluyen clat/clon (centro del píxel), c (canal),
    tb (temperatura de brillo, K), csunzen y cloctime. Ojo: los canales 1-2 son
    solares y su `tb` no es una temperatura; el preset ya pide 3-9 (térmicos).
    Para LOLA, lat/lon/radio.
    El GDS devuelve CSV si el área es pequeña y .tab (sin cabecera) si es grande;
    en ese caso las columnas se recuperan del comentario del propio archivo.
    """
    import io

    import pandas as pd

    res = gds_query(query, bbox, **extra)
    urls = [f["url"] for f in res["files"]]
    csv_url = next((u for u in urls if u.endswith(".csv")), None)
    tab_url = next((u for u in urls if u.endswith(".tab")), None)

    if csv_url:
        df = pd.read_csv(io.StringIO(get(csv_url, timeout=300).text))
        origen = csv_url
    elif tab_url:
        texto = get(tab_url, timeout=300).text
        cabecera = None
        for linea in texto.splitlines():
            if linea.startswith("#") and "," in linea and "date" in linea.lower():
                cabecera = [c.strip() for c in linea.lstrip("#").strip().split(",")]
        df = pd.read_csv(io.StringIO(texto), comment="#", header=None, skipinitialspace=True)
        if cabecera and len(cabecera) == df.shape[1]:
            df.columns = cabecera
        origen = tab_url
    else:
        raise RuntimeError(
            "GDS no generó tabla de datos "
            f"(observaciones={res['count']}, estado={res['state']}, error={res['error']})"
        )

    df.columns = [str(c).strip() for c in df.columns]
    if dest:
        download(origen, dest)
    return df
