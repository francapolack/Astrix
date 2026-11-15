"""Pruebas de similitud, promedio ponderado y orden del ranking."""

import pytest

from core.logic import (
    calcular_puntajes,
    puntaje_total,
    rankear_sitios,
    similitud_parametro,
)

DESTINO = {
    "id": "luna",
    "nombre": "Luna",
    "valores": {"elevacion": 0.5, "polvo": 0.25},
}


def _sitio(
    identificador: str,
    nombre: str,
    elevacion: float,
    polvo: float,
) -> dict:
    """Arma un sitio mínimo para las pruebas."""
    return {
        "id": identificador,
        "nombre": nombre,
        "valores": {"elevacion": elevacion, "polvo": polvo},
    }


def test_similitud_igual_devuelve_uno():
    assert similitud_parametro(0.7, 0.7) == 1.0


def test_similitud_es_uno_menos_la_diferencia():
    assert similitud_parametro(0.8, 0.6) == pytest.approx(0.8)
    assert similitud_parametro(0.1, 0.9) == pytest.approx(0.2)


def test_similitud_es_simetrica():
    assert similitud_parametro(0.2, 0.9) == pytest.approx(
        similitud_parametro(0.9, 0.2)
    )


@pytest.mark.parametrize("valor", [-0.1, 1.1, "0.5", None, True])
def test_similitud_rechaza_valores_invalidos(valor):
    with pytest.raises(ValueError):
        similitud_parametro(valor, 0.5)


def test_calcular_puntajes_por_parametro():
    sitio = _sitio("a", "Sitio A", 0.6, 0.25)

    puntajes = calcular_puntajes(
        sitio,
        DESTINO,
        {"elevacion": 2, "polvo": 3},
    )

    assert puntajes == {
        "elevacion": pytest.approx(0.9),
        "polvo": pytest.approx(1.0),
    }


def test_calcular_puntajes_ignora_peso_cero():
    sitio = _sitio("a", "Sitio A", 0.6, 0.25)

    puntajes = calcular_puntajes(
        sitio,
        DESTINO,
        {"elevacion": 2, "polvo": 0},
    )

    assert puntajes == {"elevacion": pytest.approx(0.9)}


def test_calcular_puntajes_sin_parametros_falla():
    sitio = _sitio("a", "Sitio A", 0.6, 0.25)

    with pytest.raises(ValueError):
        calcular_puntajes(sitio, DESTINO, {})


def test_calcular_puntajes_todos_con_peso_cero_falla():
    sitio = _sitio("a", "Sitio A", 0.6, 0.25)

    with pytest.raises(ValueError):
        calcular_puntajes(sitio, DESTINO, {"elevacion": 0, "polvo": 0})


def test_calcular_puntajes_sin_valor_en_sitio_falla():
    sitio = {"id": "a", "nombre": "Sitio A", "valores": {"elevacion": 0.5}}

    with pytest.raises(ValueError, match="polvo"):
        calcular_puntajes(sitio, DESTINO, {"polvo": 1})


def test_calcular_puntajes_sin_valor_en_destino_falla():
    sitio = _sitio("a", "Sitio A", 0.5, 0.5)
    destino = {"id": "luna", "nombre": "Luna", "valores": {"elevacion": 0.5}}

    with pytest.raises(ValueError, match="polvo"):
        calcular_puntajes(sitio, destino, {"polvo": 1})


def test_puntaje_total_es_el_promedio_ponderado():
    puntajes = {"a": 1.0, "b": 0.5}
    pesos = {"a": 2, "b": 1}
    assert puntaje_total(puntajes, pesos) == pytest.approx((2 * 1.0 + 1 * 0.5) / 3)


def test_puntaje_total_un_solo_parametro_activo():
    puntajes = {"a": 0.4, "b": 0.9}
    pesos = {"a": 0, "b": 3}
    assert puntaje_total(puntajes, pesos) == pytest.approx(0.9)


def test_puntaje_total_sin_puntajes_falla():
    with pytest.raises(ValueError):
        puntaje_total({}, {"a": 1})


def test_ranking_ordena_de_mayor_a_menor():
    sitios = [
        _sitio("lejos", "Lejos", 0.0, 0.25),
        _sitio("cerca", "Cerca", 0.5, 0.25),
        _sitio("medio", "Medio", 0.75, 0.25),
    ]

    ranking = rankear_sitios(
        sitios,
        DESTINO,
        {"elevacion": 1, "polvo": 1},
    )

    assert [resultado.sitio["id"] for resultado in ranking] == [
        "cerca",
        "medio",
        "lejos",
    ]
    assert ranking[0].total == pytest.approx(1.0)
    assert ranking[-1].total == pytest.approx(0.75)


def test_ranking_pesos_distintos_cambia_el_orden():
    sitios = [
        _sitio("a", "A", 1.0, 0.0),
        _sitio("b", "B", 0.0, 0.25),
    ]
    # Con más peso en polvo, B debe quedar primero.
    ranking = rankear_sitios(
        sitios,
        DESTINO,
        {"elevacion": 1, "polvo": 4},
    )

    assert [resultado.sitio["id"] for resultado in ranking] == ["b", "a"]


def test_ranking_desempata_por_nombre():
    sitios = [
        _sitio("z", "Zeta", 0.6, 0.25),
        _sitio("a", "alfa", 0.4, 0.25),
    ]

    ranking = rankear_sitios(
        sitios,
        DESTINO,
        {"elevacion": 1, "polvo": 1},
    )

    assert [resultado.sitio["nombre"] for resultado in ranking] == [
        "alfa",
        "Zeta",
    ]


def test_ranking_sin_sitios_devuelve_lista_vacia():
    assert rankear_sitios([], DESTINO, {"elevacion": 1}) == []


def test_ranking_incluye_puntajes_por_parametro():
    sitio = _sitio("a", "Sitio A", 0.6, 0.25)

    resultado = rankear_sitios(
        [sitio],
        DESTINO,
        {"elevacion": 1, "polvo": 1},
    )[0]

    assert resultado.puntajes["elevacion"] == pytest.approx(0.9)
    assert resultado.puntajes["polvo"] == pytest.approx(1.0)


def test_ranking_ignora_parametros_con_peso_cero():
    sitio = _sitio("a", "Sitio A", 0.6, 0.25)

    resultado = rankear_sitios(
        [sitio],
        DESTINO,
        {"elevacion": 2, "polvo": 0},
    )[0]

    assert resultado.puntajes == {"elevacion": pytest.approx(0.9)}
    assert resultado.total == pytest.approx(0.9)