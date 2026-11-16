"""JAXA — G-Portal y ALOS World 3D (AW3D30).

Estado real (comprobado): JAXA **no** ofrece acceso anónimo.
- G-Portal (https://gportal.jaxa.jp) exige cuenta y su API usa OAuth2
  (client_id / client_secret que se generan en tu perfil).
- AW3D30 se descarga tras registrarse en https://www.eorc.jaxa.jp/ALOS/aw3d30/

Por eso este módulo:
1. construye los identificadores de tesela AW3D30 (1°x1°, 30 m),
2. deja lista la llamada autenticada a G-Portal,
3. documenta las alternativas sin registro (USGS STAC, PDS, OpenTopography).

Alternativas ya integradas en este paquete para datos japoneses de Luna/Marte:
- Kaguya/SELENE Terrain Camera DTM -> nsac.sources.usgs_stac
  ('kaguya_terrain_camera_usgs_dtms_v2' y variantes polares)
- Kaguya TC y SP -> PDS (nsac.sources.pds)
"""

from __future__ import annotations

import os
from typing import Any

from ..http import get_json, post_json

GPORTAL_TOKEN = "https://gportal.jaxa.jp/gpr/api/token"
GPORTAL_SEARCH = "https://gportal.jaxa.jp/gpr/api/search"
INFO = {
    "portal": "https://gportal.jaxa.jp/gpr/index/index",
    "api_docs": "https://gportal.jaxa.jp/gpr/help/en/api.html",
    "aw3d30": "https://www.eorc.jaxa.jp/ALOS/aw3d30/index.htm",
    "requiere_cuenta": True,
}


def aw3d30_tile(lat: float, lon: float) -> str:
    """Nombre de tesela AW3D30 de 1°x1° que contiene el punto.

    Convención: N/S + latitud del borde inferior (3 dígitos) + E/W + longitud
    del borde oeste (3 dígitos). Ej.: (35.4, 135.7) -> 'N035E135'.
    """
    lat_i = int(abs(lat)) * (1 if lat >= 0 else -1)
    lon_i = int(abs(lon)) * (1 if lon >= 0 else -1)
    ns = "N" if lat >= 0 else "S"
    ew = "E" if lon >= 0 else "W"
    return f"{ns}{abs(lat_i):03d}{ew}{abs(lon_i):03d}"


def aw3d30_tiles_for_bbox(bbox: tuple[float, float, float, float]) -> list[str]:
    """Todas las teselas 1°x1° que cubren un bbox (oeste, sur, este, norte)."""
    w, s, e, n = bbox
    tiles = []
    lat = int(s)
    while lat < n:
        lon = int(w)
        while lon < e:
            tiles.append(aw3d30_tile(lat, lon))
            lon += 1
        lat += 1
    return tiles


def gportal_token(
    client_id: str | None = None, client_secret: str | None = None
) -> str:
    """Token OAuth2 de G-Portal (necesita cuenta gratuita)."""
    client_id = client_id or os.getenv("GPORTAL_CLIENT_ID")
    client_secret = client_secret or os.getenv("GPORTAL_CLIENT_SECRET")
    if not client_id or not client_secret:
        raise RuntimeError(
            "Faltan GPORTAL_CLIENT_ID / GPORTAL_CLIENT_SECRET. "
            "Se generan en https://gportal.jaxa.jp (Mi cuenta > API)."
        )
    data = post_json(
        GPORTAL_TOKEN,
        data={
            "grant_type": "client_credentials",
            "client_id": client_id,
            "client_secret": client_secret,
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    return data["access_token"]


def gportal_search(dataset: str, bbox: tuple[float, float, float, float], token: str | None = None) -> Any:
    """Búsqueda genérica en G-Portal (dataset p.ej. 'ALOS_AVNIR2', 'ALOS_PALSAR').

    Nota: el nombre de parámetros puede variar según el dataset; revisa la
    documentación en INFO['api_docs'] antes de confiar en el resultado.
    """
    token = token or gportal_token()
    payload = {"dataset": dataset, "bbox": list(bbox), "limit": 20}
    return post_json(GPORTAL_SEARCH, payload, headers={"Authorization": f"Bearer {token}"})


def check() -> dict[str, Any]:
    """Comprueba si hay credenciales configuradas (sin llamar a la API)."""
    return {
        "credenciales": bool(os.getenv("GPORTAL_CLIENT_ID") and os.getenv("GPORTAL_CLIENT_SECRET")),
        **INFO,
    }
