"""Similitud y ranking de sitios frente a un destino.

Este módulo no importa Flet ni lee archivos: recibe datos ya cargados y
devuelve números. La interfaz solo muestra el resultado.
"""

from __future__ import annotations

from dataclasses import dataclass

MINIMO = 0.0
MAXIMO = 1.0


@dataclass(frozen=True)
class ResultadoAnalogo:
    """Puntaje de un sitio para los parámetros elegidos."""

    sitio: dict
    puntajes: dict[str, float]
    total: float


def similitud_parametro(valor_sitio: float, valor_destino: float) -> float:
    """Diferencia normalizada: 1 es igual y 0 es opuesto."""
    _validar_valor(valor_sitio, "sitio")
    _validar_valor(valor_destino, "destino")
    return 1 - abs(valor_sitio - valor_destino)


def _pesos_activos(pesos: dict) -> dict[str, float]:
    """Filtra los parámetros con peso mayor a cero y valida los pesos."""
    if not isinstance(pesos, dict) or not pesos:
        raise ValueError("Hay que elegir al menos un parámetro.")
    activos: dict[str, float] = {}
    for parametro, peso in pesos.items():
        if not isinstance(parametro, str) or not parametro.strip():
            raise ValueError("El id del parámetro debe ser un texto no vacío.")
        if isinstance(peso, bool) or not isinstance(peso, (int, float)):
            raise ValueError("El peso debe ser un número.")
        if peso < 0 or peso > 10:
            raise ValueError("El peso debe estar entre 0 y 10.")
        if peso > 0:
            activos[parametro] = float(peso)
    if not activos:
        raise ValueError("Hay que elegir al menos un parámetro con peso mayor a 0.")
    if len(activos) != len(set(activos)):
        raise ValueError("La lista de parámetros tiene ids repetidos.")
    return activos


def calcular_puntajes(
    sitio: dict,
    destino: dict,
    pesos: dict,
) -> dict[str, float]:
    """Calcula la similitud de cada parámetro con peso mayor a cero."""
    activos = _pesos_activos(pesos)

    valores_sitio = sitio.get("valores", {})
    valores_destino = destino.get("valores", {})
    puntajes: dict[str, float] = {}
    for parametro in activos:
        if parametro not in valores_sitio:
            raise ValueError(
                f"El sitio '{sitio.get('id')}' no tiene el parámetro "
                f"'{parametro}'."
            )
        if parametro not in valores_destino:
            raise ValueError(
                f"El destino '{destino.get('id')}' no tiene el parámetro "
                f"'{parametro}'."
            )
        puntajes[parametro] = similitud_parametro(
            valores_sitio[parametro],
            valores_destino[parametro],
        )
    return puntajes


def puntaje_total(puntajes: dict[str, float], pesos: dict) -> float:
    """Promedio ponderado de los puntajes elegidos."""
    activos = _pesos_activos(pesos)
    if not puntajes:
        raise ValueError("No hay puntajes para promediar.")
    seleccionados = {parametro for parametro in puntajes if parametro in activos}
    if not seleccionados:
        raise ValueError("No hay puntajes para promediar.")
    numerador = sum(
        activos[parametro] * puntajes[parametro]
        for parametro in seleccionados
        if parametro in puntajes
    )
    denominador = sum(activos[parametro] for parametro in seleccionados)
    if denominador <= 0:
        raise ValueError("La suma de los pesos debe ser mayor a cero.")
    return numerador / denominador


def rankear_sitios(
    sitios: list[dict],
    destino: dict,
    pesos: dict,
) -> list[ResultadoAnalogo]:
    """Ordena los sitios de mayor a menor similitud ponderada.

    Ante un empate se ordena por nombre del sitio para que el resultado sea
    estable entre ejecuciones.
    """
    activos = _pesos_activos(pesos)
    resultados: list[ResultadoAnalogo] = []
    for sitio in sitios:
        puntajes = calcular_puntajes(sitio, destino, activos)
        resultados.append(
            ResultadoAnalogo(
                sitio=sitio,
                puntajes=puntajes,
                total=puntaje_total(puntajes, activos),
            )
        )
    return sorted(
        resultados,
        key=lambda resultado: (
            -resultado.total,
            resultado.sitio["nombre"].casefold(),
        ),
    )


def _validar_valor(valor: float, origen: str) -> None:
    """Rechaza valores que no sean números normalizados entre 0 y 1."""
    if isinstance(valor, bool) or not isinstance(valor, (int, float)):
        raise ValueError(f"El valor del {origen} debe ser un número.")
    if not MINIMO <= valor <= MAXIMO:
        raise ValueError(
            f"El valor del {origen} debe estar entre 0 y 1, no {valor}."
        )
