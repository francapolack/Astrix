"""Alaska Satellite Facility (ASF): SAR de la Tierra (Sentinel-1, RADARSAT-2...).

Búsqueda abierta; la descarga requiere Earthdata Login (earthaccess).
Útil para textura SAR de análogos terrestres (rugosidad, humedad, hielo).
"""

from __future__ import annotations

from typing import Any

from ..http import get_json

API = "https://api.daac.asf.alaska.edu/services/search/param"


def search(
    platform: str | None = None,
    bbox: tuple[float, float, float, float] | None = None,
    start: str | None = None,
    end: str | None = None,
    max_results: int = 20,
    processing_level: str | None = None,
) -> list[dict[str, Any]]:
    """Busca escenas SAR.

    platform: 'Sentinel-1', 'RADARSAT-2', 'ALOS PALSAR', 'SMAP'...
    bbox = (sur, oeste, norte, este)  -- ojo: ASF usa este orden.
    """
    params: dict[str, Any] = {"output": "json", "maxResults": max_results}
    if platform:
        params["platform"] = platform
    if bbox:
        params["bbox"] = ",".join(str(v) for v in bbox)
    if start:
        params["start"] = start
    if end:
        params["end"] = end
    if processing_level:
        params["processingLevel"] = processing_level

    data = get_json(API, params=params)
    results = data[0] if data and isinstance(data[0], list) else []
    out = []
    for g in results:
        out.append(
            {
                "granule": g.get("granuleName"),
                "platform": g.get("platform"),
                "beam_mode": g.get("beamModeType"),
                "start": g.get("startTime"),
                "center_lat": g.get("centerLat"),
                "center_lon": g.get("centerLon"),
                "download": g.get("downloadUrl"),
                "size_mb": round(int(g.get("bytes") or g.get("granuleSize") or 0) / 1e6, 1) or None,
            }
        )
    return out
