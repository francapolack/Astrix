"""Utilidades HTTP compartidas: sesión con reintentos, JSON y descargas."""

from __future__ import annotations

import os
import re
import warnings
from pathlib import Path
from typing import Any, Iterator
from urllib.parse import urlparse

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

USER_AGENT = "nsac-spaceapps/0.1 (NASA Space Apps 2026; python-requests)"

DATA_DIR = Path(os.getenv("NSAC_DATA_DIR", "./data")).expanduser()

# Hosts con cadena de certificados problemática. El portal de datos de la CSA
# usa un certificado emitido por Entrust, y las CA de Entrust se retiraron de
# los almacenes de confianza en 2025: Python/curl fallan aunque el navegador
# funcione. Añade hosts aquí (o en NSAC_INSECURE_HOSTS) si te pasa lo mismo.
FALLBACK_INSECURE_HOSTS = {
    h.strip()
    for h in os.getenv(
        "NSAC_INSECURE_HOSTS", "donnees-data.asc-csa.gc.ca,www.eodms-sgdot.nrcan-rncan.gc.ca"
    ).split(",")
    if h.strip()
}

_warned: set[str] = set()


def _verify_ssl() -> bool:
    return os.getenv("NSAC_VERIFY_SSL", "1").lower() not in ("0", "false", "no")


def _send(session: requests.Session, method: str, url: str, **kwargs: Any) -> requests.Response:
    """GET/POST con reintento sin verificar TLS sólo para hosts conocidos."""
    kwargs.setdefault("timeout", 90)
    try:
        return session.request(method, url, **kwargs)
    except requests.exceptions.SSLError:
        host = urlparse(url).hostname or ""
        if not _verify_ssl() or host not in FALLBACK_INSECURE_HOSTS:
            raise
        if host not in _warned:
            _warned.add(host)
            warnings.warn(
                f"{host} presenta un certificado no verificable (CA Entrust retirada). "
                "Continúo sin verificar TLS sólo para este host.",
                stacklevel=2,
            )
        kwargs["verify"] = False
        return session.request(method, url, **kwargs)


_session: requests.Session | None = None


def get_session() -> requests.Session:
    """Sesión reutilizable con reintentos y User-Agent propio."""
    global _session
    if _session is None:
        s = requests.Session()
        s.headers.update({"User-Agent": USER_AGENT, "Accept": "application/json, */*"})
        retry = Retry(
            total=3,
            backoff_factor=0.6,
            status_forcelist=(429, 500, 502, 503, 504),
            allowed_methods=frozenset(["GET", "POST"]),
        )
        s.mount("https://", HTTPAdapter(max_retries=retry))
        s.mount("http://", HTTPAdapter(max_retries=retry))
        s.verify = _verify_ssl()
        _session = s
    return _session


def get(url: str, **kwargs: Any) -> requests.Response:
    resp = _send(get_session(), "GET", url, **kwargs)
    resp.raise_for_status()
    return resp


def post(url: str, payload: dict | None = None, **kwargs: Any) -> requests.Response:
    # `data=` (formularios OAuth2) y `json=` son excluyentes: solo añadimos
    # json cuando el llamador no ha pasado ya un cuerpo.
    if payload is not None:
        kwargs.setdefault("json", payload)
    resp = _send(get_session(), "POST", url, **kwargs)
    resp.raise_for_status()
    return resp


def get_json(url: str, **kwargs: Any) -> Any:
    return get(url, **kwargs).json()


def post_json(url: str, payload: dict | None = None, **kwargs: Any) -> Any:
    return post(url, payload, **kwargs).json()


def safe_filename(url: str) -> str:
    name = re.split(r"[?#]", url.rsplit("/", 1)[-1])[0]
    return name or "archivo"


def download(
    url: str,
    dest: str | Path | None = None,
    chunk_size: int = 1 << 20,
    headers: dict[str, str] | None = None,
) -> Path:
    """Descarga en streaming. `dest` puede ser una carpeta o una ruta de archivo.

    `headers` sirve para tokens (p.ej. Authorization: Bearer de CDSE).
    """
    if dest is None:
        dest = DATA_DIR / "downloads"
    dest = Path(dest)
    if dest.is_dir() or dest.suffix == "":
        dest = dest / safe_filename(url)
    dest.parent.mkdir(parents=True, exist_ok=True)

    with _send(get_session(), "GET", url, stream=True, timeout=180, headers=headers) as resp:
        resp.raise_for_status()
        with dest.open("wb") as fh:
            for chunk in resp.iter_content(chunk_size=chunk_size):
                if chunk:
                    fh.write(chunk)
    return dest


def iter_lines(url: str, **kwargs: Any) -> Iterator[str]:
    """Lee un archivo de texto remoto línea a línea (útil para .tab del GDS)."""
    with _send(get_session(), "GET", url, stream=True, timeout=180, **kwargs) as resp:
        resp.raise_for_status()
        for line in resp.iter_lines(decode_unicode=True):
            if line:
                yield line
