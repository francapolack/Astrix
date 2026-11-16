"""Pruebas del historial persistente de búsquedas."""

import copy
import json
from datetime import datetime
from pathlib import Path

import pytest

from core.repository import (
    ARCHIVO_HISTORIAL,
    CAMPOS_HISTORIAL,
    ErrorDatos,
    borrar_busqueda,
    cargar_historial,
    guardar_busqueda,
)

CATEGORIAS = [
    {
        "id": "topografia",
        "nombre": "Topografía",
        "descripcion": "Relieve del terreno.",
        "parametros": [
            {"id": "elevacion", "nombre": "Elevación"},
            {"id": "pendiente", "nombre": "Pendiente"},
        ],
    },
    {
        "id": "geologia",
        "nombre": "Geología",
        "descripcion": "Composición del suelo.",
        "parametros": [
            {"id": "composicion", "nombre": "Composición del suelo"},
        ],
    },
]

DESTINO = {"id": "luna", "nombre": "Luna"}


def _entrada_valida(entrada_id: str = "busqueda-1") -> dict:
    """Una entrada con la estructura completa que exige el contrato."""
    return {
        "id": entrada_id,
        "fecha": "2026-11-14T10:30:00",
        "destino_id": "luna",
        "destino_nombre": "Luna",
        "parametros": ["elevacion", "pendiente"],
        "pesos": {"elevacion": 5, "pendiente": 5},
        "categorias": ["Topografía"],
    }


def _historial_valido() -> list[dict]:
    """Una lista de una sola entrada válida."""
    return [_entrada_valida()]


def _escribir(tmp_path: Path, contenido) -> Path:
    """Guarda un historial JSON de prueba en la carpeta temporal."""
    ruta = tmp_path / ARCHIVO_HISTORIAL
    ruta.write_text(
        json.dumps(contenido, ensure_ascii=False),
        encoding="utf-8",
    )
    return ruta


def test_historial_ausente_es_vacio(tmp_path):
    assert cargar_historial(tmp_path) == []


@pytest.mark.parametrize("contenido", ["", "   \n", "\n\t "])
def test_historial_vacio_es_vacio(tmp_path, contenido):
    (tmp_path / ARCHIVO_HISTORIAL).write_text(contenido, encoding="utf-8")

    assert cargar_historial(tmp_path) == []


def test_cargar_historial_valido(tmp_path):
    historial = _historial_valido()
    _escribir(tmp_path, historial)

    assert cargar_historial(tmp_path) == historial


def test_json_invalido_falla(tmp_path):
    (tmp_path / ARCHIVO_HISTORIAL).write_text("{no es json", encoding="utf-8")

    with pytest.raises(ErrorDatos, match="JSON válido"):
        cargar_historial(tmp_path)


def test_historial_que_no_es_lista_falla(tmp_path):
    _escribir(tmp_path, {"id": "busqueda-1"})

    with pytest.raises(ErrorDatos, match="debe contener una lista"):
        cargar_historial(tmp_path)


@pytest.mark.parametrize("campo", CAMPOS_HISTORIAL)
def test_campo_faltante_falla(tmp_path, campo):
    historial = _historial_valido()
    del historial[0][campo]
    _escribir(tmp_path, historial)

    with pytest.raises(ErrorDatos, match=campo):
        cargar_historial(tmp_path)


@pytest.mark.parametrize("entrada_id", ["", "   ", 123, None])
def test_id_invalido_falla(tmp_path, entrada_id):
    historial = _historial_valido()
    historial[0]["id"] = entrada_id
    _escribir(tmp_path, historial)

    with pytest.raises(ErrorDatos, match="id inválido"):
        cargar_historial(tmp_path)


def test_id_repetido_falla(tmp_path):
    historial = [
        _entrada_valida("repetida"),
        _entrada_valida("repetida"),
    ]
    _escribir(tmp_path, historial)

    with pytest.raises(ErrorDatos, match="repetido"):
        cargar_historial(tmp_path)


@pytest.mark.parametrize("fecha", ["ayer", "", 123, None])
def test_fecha_invalida_falla(tmp_path, fecha):
    historial = _historial_valido()
    historial[0]["fecha"] = fecha
    _escribir(tmp_path, historial)

    with pytest.raises(ErrorDatos, match="fecha"):
        cargar_historial(tmp_path)


@pytest.mark.parametrize("campo", ["destino_id", "destino_nombre"])
@pytest.mark.parametrize("valor", ["", "   ", 123])
def test_destino_invalido_falla(tmp_path, campo, valor):
    historial = _historial_valido()
    historial[0][campo] = valor
    _escribir(tmp_path, historial)

    with pytest.raises(ErrorDatos, match=campo):
        cargar_historial(tmp_path)


@pytest.mark.parametrize("valor", [[], "elevacion", [""], [123]])
def test_parametros_invalidos_fallan(tmp_path, valor):
    historial = _historial_valido()
    historial[0]["parametros"] = valor
    _escribir(tmp_path, historial)

    with pytest.raises(ErrorDatos, match="parametros"):
        cargar_historial(tmp_path)


@pytest.mark.parametrize("valor", [[], "Topografía", [""], [123]])
def test_categorias_invalidas_fallan(tmp_path, valor):
    historial = _historial_valido()
    historial[0]["categorias"] = valor
    _escribir(tmp_path, historial)

    with pytest.raises(ErrorDatos, match="categorias"):
        cargar_historial(tmp_path)


def test_parametros_repetidos_fallan(tmp_path):
    historial = _historial_valido()
    historial[0]["parametros"] = ["elevacion", "elevacion"]
    _escribir(tmp_path, historial)

    with pytest.raises(ErrorDatos, match="repetidos"):
        cargar_historial(tmp_path)


def test_guardar_busqueda_crea_el_archivo(tmp_path):
    entrada = guardar_busqueda(
        DESTINO,
        {"elevacion": 5},
        CATEGORIAS,
        tmp_path,
    )

    assert entrada["destino_id"] == "luna"
    assert entrada["destino_nombre"] == "Luna"
    assert entrada["parametros"] == ["elevacion"]
    assert entrada["categorias"] == ["Topografía"]
    datetime.fromisoformat(entrada["fecha"])
    assert cargar_historial(tmp_path) == [entrada]


def test_guardar_busqueda_deriva_categorias_en_orden_del_catalogo(tmp_path):
    entrada = guardar_busqueda(
        DESTINO,
        {"composicion": 5, "elevacion": 5},
        CATEGORIAS,
        tmp_path,
    )

    assert entrada["categorias"] == ["Topografía", "Geología"]


def test_guardar_busqueda_agrega_la_mas_reciente_primero(tmp_path):
    primera = guardar_busqueda(DESTINO, {"elevacion": 5}, CATEGORIAS, tmp_path)
    segunda = guardar_busqueda(
        DESTINO,
        {"pendiente": 5, "composicion": 5},
        CATEGORIAS,
        tmp_path,
    )

    historial = cargar_historial(tmp_path)
    assert [entrada["id"] for entrada in historial] == [
        segunda["id"],
        primera["id"],
    ]
    assert len({entrada["id"] for entrada in historial}) == 2


def test_guardar_busqueda_escribe_utf8_legible(tmp_path):
    guardar_busqueda(DESTINO, {"elevacion": 5, "composicion": 5}, CATEGORIAS, tmp_path)

    texto = (tmp_path / ARCHIVO_HISTORIAL).read_text(encoding="utf-8")
    assert "Geología" in texto
    assert "Topografía" in texto


def test_guardar_busqueda_no_deja_archivo_temporal(tmp_path):
    guardar_busqueda(DESTINO, {"elevacion": 5}, CATEGORIAS, tmp_path)

    assert not (tmp_path / f"{ARCHIVO_HISTORIAL}.tmp").exists()


def test_guardar_busqueda_no_sobrescribe_un_archivo_corrupto(tmp_path):
    ruta = tmp_path / ARCHIVO_HISTORIAL
    ruta.write_text("{roto", encoding="utf-8")

    with pytest.raises(ErrorDatos, match="JSON válido"):
        guardar_busqueda(DESTINO, {"elevacion": 5}, CATEGORIAS, tmp_path)

    assert ruta.read_text(encoding="utf-8") == "{roto"


@pytest.mark.parametrize(
    ("destino", "parametros"),
    [
        ({}, {"elevacion": 5}),
        ({"id": "", "nombre": "Luna"}, {"elevacion": 5}),
        ({"id": "luna", "nombre": " "}, {"elevacion": 5}),
        (DESTINO, {}),
        (DESTINO, {"desconocido": 5}),
        (DESTINO, {"elevacion": 0}),
        (DESTINO, {"": 5}),
    ],
)
def test_guardar_busqueda_valida_los_argumentos(tmp_path, destino, parametros):
    with pytest.raises(ValueError):
        guardar_busqueda(destino, parametros, CATEGORIAS, tmp_path)


def test_borrar_busqueda_deja_las_demas(tmp_path):
    primera = guardar_busqueda(DESTINO, {"elevacion": 5}, CATEGORIAS, tmp_path)
    segunda = guardar_busqueda(DESTINO, {"pendiente": 5}, CATEGORIAS, tmp_path)

    restante = borrar_busqueda(primera["id"], tmp_path)

    assert [entrada["id"] for entrada in restante] == [segunda["id"]]
    assert cargar_historial(tmp_path) == restante


def test_borrar_ultima_busqueda_deja_historial_vacio(tmp_path):
    entrada = guardar_busqueda(DESTINO, {"elevacion": 5}, CATEGORIAS, tmp_path)

    assert borrar_busqueda(entrada["id"], tmp_path) == []
    assert cargar_historial(tmp_path) == []


def test_borrar_busqueda_inexistente_falla(tmp_path):
    _escribir(tmp_path, _historial_valido())

    with pytest.raises(ErrorDatos, match="No se encontró"):
        borrar_busqueda("no-existe", tmp_path)


def test_borrar_busqueda_con_historial_corrupto_falla(tmp_path):
    (tmp_path / ARCHIVO_HISTORIAL).write_text("{roto", encoding="utf-8")

    with pytest.raises(ErrorDatos, match="JSON válido"):
        borrar_busqueda("busqueda-1", tmp_path)


def test_historial_se_copia_para_no_compartir_estado(tmp_path):
    historial = _historial_valido()
    _escribir(tmp_path, historial)
    original = copy.deepcopy(historial)

    cargado = cargar_historial(tmp_path)
    cargado[0]["parametros"].append("pendiente")

    assert historial == original
