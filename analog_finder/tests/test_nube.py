"""Pruebas del cliente de la nube (core/nube.py).

Las llamadas HTTP se simulan con un módulo `requests` falso; nada de estas
pruebas toca la red. El catálogo real se usa para validar el perfil.
"""

import json
from pathlib import Path

import pytest
import requests

from core.nube import (
    CLAVE_OBJETIVO,
    ErrorNube,
    adaptar_sitio_nube,
    buscar_analogos,
    cargar_credenciales,
    construir_perfil,
    datos_sitio,
    extraer_analogos_tierra,
    extraer_sitio_objetivo,
    textos_del_desglose,
)
from core.repository import cargar_categorias

CATEGORIAS_REALES = cargar_categorias()


class _RespuestaFalsa:
    """Imita el objeto de respuesta de requests."""

    def __init__(self, estado: int, cuerpo) -> None:
        self.status_code = estado
        self._cuerpo = cuerpo
        self.text = (
            cuerpo if isinstance(cuerpo, str) else json.dumps(cuerpo)
        )

    def json(self):
        if isinstance(self._cuerpo, str):
            raise ValueError("no es JSON")
        return self._cuerpo


class _RequestsFalso:
    """Imita requests.post / requests.get con salidas configuradas."""

    RequestException = requests.RequestException

    def __init__(self, respuesta=None, error: Exception | None = None):
        self.respuesta = respuesta
        self.error = error
        self.ultima_url = ""
        self.ultimo_json = None
        self.ultimos_headers: dict = {}

    def post(self, url, headers=None, json=None, timeout=None):
        self.ultima_url = url
        self.ultimo_json = json
        self.ultimos_headers = headers or {}
        if self.error is not None:
            raise self.error
        return self.respuesta

    def get(self, url, headers=None, params=None, timeout=None):
        self.ultima_url = url
        self.ultimos_headers = headers or {}
        if self.error is not None:
            raise self.error
        return self.respuesta


RESPUESTA_V2 = {
    "perfil_aplicado": {},
    "luna_top1": {
        "sitio_id": "luna@-86.6,0.09±0.05",
        "nombre": "Malapert",
        "tipo": "Cráter",
        "cuerpo": "luna",
        "lat": -86.6,
        "lon": 0.09,
        "similitud": 0.9,
        "similitudes": {
            "topografia": 0.8,
            "termico": 0.6,
            "superficie": None,
            "iluminacion": 0.9,
            "global": 0.9,
        },
    },
    "marte_top1": None,
    "tierra_top5": [
        {
            "sitio_id": "tierra@-24.08,-69.47±0.05",
            "nombre": "Atacama",
            "tipo": "Desierto",
            "cuerpo": "tierra",
            "lat": -24.08,
            "lon": -69.47,
            "similitud": 0.75,
            "similitudes": {
                "topografia": 0.9,
                "termico": 0.3,
                "superficie": 0.6,
                "iluminacion": None,
                "global": 0.75,
            },
        }
    ],
}


# ---------------------------------------------------------------------------
# Credenciales
# ---------------------------------------------------------------------------

def test_falta_env(tmp_path):
    with pytest.raises(ErrorNube, match="Falta el archivo .env"):
        cargar_credenciales(tmp_path / ".env")


def test_env_sin_url(tmp_path):
    ruta = tmp_path / ".env"
    ruta.write_text("SUPABASE_KEY=sk_prueba\n", encoding="utf-8")
    with pytest.raises(ErrorNube, match="SUPABASE_URL"):
        cargar_credenciales(ruta)


def test_env_sin_clave(tmp_path):
    ruta = tmp_path / ".env"
    ruta.write_text("SUPABASE_URL=https://demo.supabase.co\n", encoding="utf-8")
    with pytest.raises(ErrorNube, match="SUPABASE_ANON_KEY"):
        cargar_credenciales(ruta)


def test_credenciales_validas(tmp_path):
    ruta = tmp_path / ".env"
    ruta.write_text(
        "# comentario\nSUPABASE_URL=https://demo.supabase.co/\n"
        "SUPABASE_ANON_KEY=anon_prueba\n",
        encoding="utf-8",
    )
    url, clave = cargar_credenciales(ruta)
    assert url == "https://demo.supabase.co"
    assert clave == "anon_prueba"


# ---------------------------------------------------------------------------
# Perfil
# ---------------------------------------------------------------------------

def test_construir_perfil_con_catalogo_real():
    perfil = construir_perfil(
        CATEGORIAS_REALES,
        {"elevacion": -1500.0, "pendiente": 4.0},
    )
    assert perfil == {
        "elevacion_media_m": {"valor": -1500.0, "peso": 1.0},
        "pendiente_media_grados": {"valor": 4.0, "peso": 1.0},
    }


def test_perfil_vacio_falla():
    with pytest.raises(ValueError, match="al menos un parámetro"):
        construir_perfil(CATEGORIAS_REALES, {})


def test_parametro_desconocido_falla():
    with pytest.raises(ValueError, match="humedad"):
        construir_perfil(CATEGORIAS_REALES, {"humedad": 0.5})


def test_valor_fuera_de_rango_falla():
    with pytest.raises(ValueError, match="entre"):
        construir_perfil(CATEGORIAS_REALES, {"pendiente": 99.0})


def test_valor_no_numerico_falla():
    with pytest.raises(ValueError, match="número"):
        construir_perfil(CATEGORIAS_REALES, {"pendiente": "suave"})


# ---------------------------------------------------------------------------
# Llamadas RPC (con requests falso)
# ---------------------------------------------------------------------------

def test_buscar_analogos_envia_el_perfil(monkeypatch):
    falso = _RequestsFalso(_RespuestaFalsa(200, RESPUESTA_V2))
    monkeypatch.setattr("core.nube.requests", falso)

    respuesta = buscar_analogos(
        "https://demo.supabase.co",
        "clave_prueba",
        {"pendiente_media_grados": {"valor": 4.0, "peso": 1.0}},
    )
    assert respuesta == RESPUESTA_V2
    assert falso.ultima_url == (
        "https://demo.supabase.co/rest/v1/rpc/buscar_analogos_v2"
    )
    assert falso.ultimo_json == {
        "parametros": {
            "perfil": {"pendiente_media_grados": {"valor": 4.0, "peso": 1.0}}
        }
    }
    assert falso.ultimos_headers["apikey"] == "clave_prueba"


def test_buscar_analogos_error_de_red(monkeypatch):
    falso = _RequestsFalso(error=requests.ConnectionError("sin red"))
    monkeypatch.setattr("core.nube.requests", falso)
    with pytest.raises(ErrorNube, match="No se pudo conectar"):
        buscar_analogos("https://demo.supabase.co", "k", {})


def test_buscar_analogos_error_de_estado(monkeypatch):
    falso = _RequestsFalso(_RespuestaFalsa(401, "no autorizado"))
    monkeypatch.setattr("core.nube.requests", falso)
    with pytest.raises(ErrorNube, match="401"):
        buscar_analogos("https://demo.supabase.co", "k", {})


def test_buscar_analogos_respuesta_no_json(monkeypatch):
    falso = _RequestsFalso(_RespuestaFalsa(200, "texto"))
    monkeypatch.setattr("core.nube.requests", falso)
    with pytest.raises(ErrorNube, match="no es JSON"):
        buscar_analogos("https://demo.supabase.co", "k", {})


def test_datos_sitio_devuelve_la_fila(monkeypatch):
    falso = _RequestsFalso(
        _RespuestaFalsa(200, [{"sitio_id": "tierra@x", "nombre": "Atacama"}])
    )
    monkeypatch.setattr("core.nube.requests", falso)
    fila = datos_sitio("https://demo.supabase.co", "k", "tierra@x")
    assert fila["nombre"] == "Atacama"
    assert falso.ultima_url.endswith("/rest/v1/sitios_candidatos")


def test_datos_sitio_ausente_falla(monkeypatch):
    falso = _RequestsFalso(_RespuestaFalsa(200, []))
    monkeypatch.setattr("core.nube.requests", falso)
    with pytest.raises(ErrorNube, match="no está en la base"):
        datos_sitio("https://demo.supabase.co", "k", "tierra@x")


# ---------------------------------------------------------------------------
# Organización de la respuesta
# ---------------------------------------------------------------------------

def test_extraer_sitio_objetivo_luna():
    objetivo = extraer_sitio_objetivo(RESPUESTA_V2, "luna")
    assert objetivo["nombre"] == "Malapert"
    assert CLAVE_OBJETIVO == {"luna": "luna_top1", "marte": "marte_top1"}


def test_extraer_sitio_objetivo_vacio_falla():
    with pytest.raises(ErrorNube, match="ningún sitio de marte"):
        extraer_sitio_objetivo(RESPUESTA_V2, "marte")


def test_extraer_sitio_objetivo_destino_invalido():
    with pytest.raises(ErrorNube, match="no es luna ni marte"):
        extraer_sitio_objetivo(RESPUESTA_V2, "jupiter")


def test_extraer_analogos_tierra():
    analogos = extraer_analogos_tierra(RESPUESTA_V2)
    assert len(analogos) == 1
    assert analogos[0]["nombre"] == "Atacama"


def test_extraer_analogos_tierra_ausente_falla():
    with pytest.raises(ErrorNube, match="no incluye"):
        extraer_analogos_tierra({"luna_top1": {}})


def test_textos_del_desglose():
    desglose = {
        "topografia": 0.92,
        "termico": 0.3,
        "superficie": None,
        "global": 0.75,
    }
    textos = textos_del_desglose(desglose, CATEGORIAS_REALES, "Desierto")
    assert "Topografía (92 %)" in textos["similar"]
    assert "Clima térmico (30 %)" in textos["falla"]
    assert "Desierto" in textos["mision"]


def test_textos_sin_categorias_bajas():
    desglose = {"topografia": 0.8, "termico": 0.7, "global": 0.8}
    textos = textos_del_desglose(desglose, CATEGORIAS_REALES, None)
    assert "baja del 50 %" in textos["falla"]
    assert "no figura" in textos["mision"]


def test_textos_sin_dato_alguno_falla():
    with pytest.raises(ErrorNube, match="ninguna categoría con dato"):
        textos_del_desglose({"global": None}, CATEGORIAS_REALES, None)


def test_adaptar_sitio_nube():
    resultado = adaptar_sitio_nube(
        RESPUESTA_V2["tierra_top5"][0],
        CATEGORIAS_REALES,
    )
    assert resultado.total == pytest.approx(0.75)
    assert resultado.sitio["nombre"] == "Atacama"
    assert resultado.sitio["lat"] == pytest.approx(-24.08)
    assert resultado.puntajes["topografia"] == pytest.approx(0.9)
    # Las categorías sin dato no entran a los puntajes.
    assert "iluminacion" not in resultado.puntajes
    assert resultado.sitio["textos"]["similar"]
    assert resultado.sitio["es_ejemplo"] is False
