"""Pruebas de carga y validación de los archivos de datos."""

import copy
import json
from pathlib import Path

import pytest

from core.repository import (
    ErrorDatos,
    cargar_categorias,
    cargar_destinos,
    cargar_sitios,
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
    }
]

DESTINOS = [
    {
        "id": "luna",
        "nombre": "Luna",
        "zona": "Polo sur",
        "detalle": "Base permanente.",
        "es_ejemplo": True,
        "valores": {"elevacion": 0.5, "pendiente": 0.25},
    }
]

SITIOS = [
    {
        "id": "sitio_uno",
        "nombre": "Sitio Uno",
        "pais": "Chile",
        "lat": -23.5,
        "lon": -69.2,
        "es_ejemplo": True,
        "valores": {"elevacion": 0.5, "pendiente": 0.25},
        "textos": {
            "similar": "Terreno seco y despejado.",
            "falla": "Tiene atmósfera y gravedad terrestre.",
            "mision": "Probar instrumentos de campo.",
        },
    }
]


def _escribir(carpeta: Path, nombre: str, contenido) -> None:
    """Guarda un archivo JSON de prueba en la carpeta indicada."""
    ruta = carpeta / nombre
    ruta.write_text(
        json.dumps(contenido, ensure_ascii=False),
        encoding="utf-8",
    )


def _datos_validos(
    carpeta: Path,
    categorias=None,
    destinos=None,
    sitios=None,
) -> Path:
    """Crea el juego mínimo de archivos y devuelve la carpeta."""
    _escribir(
        carpeta,
        "parametros.json",
        CATEGORIAS if categorias is None else categorias,
    )
    _escribir(
        carpeta,
        "destinos.json",
        DESTINOS if destinos is None else destinos,
    )
    _escribir(
        carpeta,
        "sitios.json",
        SITIOS if sitios is None else sitios,
    )
    return carpeta


def _copia(registros: list[dict]) -> list[dict]:
    """Copia profunda para no compartir estado entre pruebas."""
    return copy.deepcopy(registros)


def test_cargar_categorias_del_proyecto():
    categorias = cargar_categorias()

    assert len(categorias) == 4
    parametros = [
        parametro
        for categoria in categorias
        for parametro in categoria["parametros"]
    ]
    assert len(parametros) == 8
    assert len({parametro["id"] for parametro in parametros}) == 8
    # Cada parámetro real trae su clave de la base y su rango físico.
    for parametro in parametros:
        assert parametro["clave_db"]
        assert "unidad" in parametro
        assert parametro["max"] > parametro["min"]


def test_cargar_destinos_del_proyecto():
    destinos = cargar_destinos()

    assert [destino["id"] for destino in destinos] == ["luna", "marte"]
    assert all(destino["es_ejemplo"] for destino in destinos)
    ids_parametros = {
        parametro["id"]
        for categoria in cargar_categorias()
        for parametro in categoria["parametros"]
    }
    for destino in destinos:
        assert set(destino["valores"]) == ids_parametros


def test_cargar_sitios_del_proyecto():
    sitios = cargar_sitios()

    assert len(sitios) == 12
    assert all(sitio["es_ejemplo"] for sitio in sitios)
    for sitio in sitios:
        assert sitio["textos"]["similar"].strip()
        assert sitio["textos"]["falla"].strip()
        assert sitio["textos"]["mision"].strip()
        assert -90.0 <= sitio["lat"] <= 90.0
        assert -180.0 <= sitio["lon"] <= 180.0


def test_carga_un_juego_valido(tmp_path):
    ruta = _datos_validos(tmp_path)

    assert cargar_categorias(ruta)[0]["id"] == "topografia"
    assert cargar_destinos(ruta)[0]["id"] == "luna"
    assert cargar_sitios(ruta)[0]["id"] == "sitio_uno"


def test_archivo_faltante_falla(tmp_path):
    _escribir(tmp_path, "parametros.json", CATEGORIAS)

    with pytest.raises(ErrorDatos, match="No se encontró"):
        cargar_destinos(tmp_path)


def test_json_invalido_falla(tmp_path):
    _datos_validos(tmp_path)
    (tmp_path / "sitios.json").write_text("{no es json", encoding="utf-8")

    with pytest.raises(ErrorDatos, match="JSON válido"):
        cargar_sitios(tmp_path)


def test_contenido_que_no_es_lista_falla(tmp_path):
    _datos_validos(tmp_path, sitios={"id": "uno"})

    with pytest.raises(ErrorDatos, match="debe contener una lista"):
        cargar_sitios(tmp_path)


def test_lista_vacia_falla(tmp_path):
    _datos_validos(tmp_path, sitios=[])

    with pytest.raises(ErrorDatos, match="no tiene registros"):
        cargar_sitios(tmp_path)


@pytest.mark.parametrize("archivo", ["parametros", "destinos", "sitios"])
def test_ids_repetidos_fallan(tmp_path, archivo):
    if archivo == "parametros":
        categorias = _copia(CATEGORIAS)
        repetida = _copia(CATEGORIAS[0])
        repetida["nombre"] = "Otra topografía"
        categorias.append(repetida)
        _datos_validos(tmp_path, categorias=categorias)
        cargador = cargar_categorias
    elif archivo == "destinos":
        destinos = _copia(DESTINOS)
        destinos.append(_copia(DESTINOS[0]))
        _datos_validos(tmp_path, destinos=destinos)
        cargador = cargar_destinos
    else:
        sitios = _copia(SITIOS)
        sitios.append(_copia(SITIOS[0]))
        _datos_validos(tmp_path, sitios=sitios)
        cargador = cargar_sitios

    with pytest.raises(ErrorDatos, match="repetido"):
        cargador(tmp_path)


def test_parametro_repetido_entre_categorias_falla(tmp_path):
    categorias = _copia(CATEGORIAS)
    categorias.append(
        {
            "id": "clima",
            "nombre": "Clima",
            "descripcion": "Temperatura.",
            "parametros": [{"id": "elevacion", "nombre": "Otra elevación"}],
        }
    )
    _datos_validos(tmp_path, categorias=categorias)

    with pytest.raises(ErrorDatos, match="repetido"):
        cargar_categorias(tmp_path)


def test_categoria_sin_parametros_falla(tmp_path):
    categorias = _copia(CATEGORIAS)
    categorias[0]["parametros"] = []
    _datos_validos(tmp_path, categorias=categorias)

    with pytest.raises(ErrorDatos, match="no tiene parámetros"):
        cargar_categorias(tmp_path)


def test_campo_faltante_en_sitio_falla(tmp_path):
    sitios = _copia(SITIOS)
    del sitios[0]["pais"]
    _datos_validos(tmp_path, sitios=sitios)

    with pytest.raises(ErrorDatos, match="'pais'"):
        cargar_sitios(tmp_path)


def test_es_ejemplo_debe_ser_booleano(tmp_path):
    sitios = _copia(SITIOS)
    sitios[0]["es_ejemplo"] = "sí"
    _datos_validos(tmp_path, sitios=sitios)

    with pytest.raises(ErrorDatos, match="es_ejemplo"):
        cargar_sitios(tmp_path)


@pytest.mark.parametrize("valor", [-0.1, 1.1, "0.5", True])
def test_valor_invalido_falla(tmp_path, valor):
    sitios = _copia(SITIOS)
    sitios[0]["valores"]["elevacion"] = valor
    _datos_validos(tmp_path, sitios=sitios)

    with pytest.raises(ErrorDatos):
        cargar_sitios(tmp_path)


def test_parametro_faltante_en_valores_falla(tmp_path):
    sitios = _copia(SITIOS)
    del sitios[0]["valores"]["pendiente"]
    _datos_validos(tmp_path, sitios=sitios)

    with pytest.raises(ErrorDatos, match="faltan valores"):
        cargar_sitios(tmp_path)


def test_parametro_desconocido_en_valores_falla(tmp_path):
    sitios = _copia(SITIOS)
    sitios[0]["valores"]["humedad"] = 0.5
    _datos_validos(tmp_path, sitios=sitios)

    with pytest.raises(ErrorDatos, match="desconocidos"):
        cargar_sitios(tmp_path)


def test_valores_que_no_son_objeto_fallan(tmp_path):
    sitios = _copia(SITIOS)
    sitios[0]["valores"] = [0.5, 0.25]
    _datos_validos(tmp_path, sitios=sitios)

    with pytest.raises(ErrorDatos, match="debe ser un objeto"):
        cargar_sitios(tmp_path)


@pytest.mark.parametrize(
    ("campo", "valor"),
    [("lat", 91.0), ("lat", -91.0), ("lon", 181.0), ("lon", -181.0)],
)
def test_coordenadas_fuera_de_rango_fallan(tmp_path, campo, valor):
    sitios = _copia(SITIOS)
    sitios[0][campo] = valor
    _datos_validos(tmp_path, sitios=sitios)

    with pytest.raises(ErrorDatos, match="fuera de rango"):
        cargar_sitios(tmp_path)


def test_coordenada_que_no_es_numero_falla(tmp_path):
    sitios = _copia(SITIOS)
    sitios[0]["lat"] = "23.5"
    _datos_validos(tmp_path, sitios=sitios)

    with pytest.raises(ErrorDatos, match="debe ser un número"):
        cargar_sitios(tmp_path)


def test_texto_faltante_falla(tmp_path):
    sitios = _copia(SITIOS)
    del sitios[0]["textos"]["falla"]
    _datos_validos(tmp_path, sitios=sitios)

    with pytest.raises(ErrorDatos, match="'falla'"):
        cargar_sitios(tmp_path)


def test_texto_vacio_falla(tmp_path):
    sitios = _copia(SITIOS)
    sitios[0]["textos"]["mision"] = "   "
    _datos_validos(tmp_path, sitios=sitios)

    with pytest.raises(ErrorDatos, match="'mision'"):
        cargar_sitios(tmp_path)


def test_textos_que_no_son_objeto_fallan(tmp_path):
    sitios = _copia(SITIOS)
    sitios[0]["textos"] = "similar"
    _datos_validos(tmp_path, sitios=sitios)

    with pytest.raises(ErrorDatos, match="debe ser un objeto"):
        cargar_sitios(tmp_path)
