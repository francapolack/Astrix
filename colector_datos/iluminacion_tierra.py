"""iluminacion_tierra.py — iluminación de la TIERRA, todo CALCULADO en local
(0 llamadas HTTP), con el mismo formato que la iluminación lunar
(rama `tierra-datos-crudos`).

La iluminación no se mide: se deriva de la geometría Sol-superficie, y la
Tierra es el caso más sencillo (día/noche cada 24 h). Cálculos:
  - fracción diurna anual: fracción de horas del año con el Sol sobre el
    horizonte, con la declinación solar aproximada (δ = 23.44°·sin(...)).
    En latitudes no polares da ~0.5; en los polos tiende a 0/1 por
    solsticios — justo el análogo terrestre de un PSR lunar.
  - energía solar media: E = S0 × sin(elevación) × transmisión_atmosférica,
    promediada sobre el año (horaria). S0 = 1361 W/m² (igual que la Luna:
    misma distancia al Sol). La ATMÓSFERA es la gran diferencia con la Luna:
    con cielo claro deja pasar ~75 % (0.75), y la nota lo dice explícitamente
    para que la comparación con la Luna no engañe.
"""

from __future__ import annotations

import math
from typing import Any

from . import constantes

# Transmisión de una atmósfera clara en horas de sol (mínimo solar: la
# irradiancia normal global en superficie ≈ 1000 W/m² de 1361 ≈ 0.73).
TRANSMISION_ATMOSFERICA = 0.75

# Declinación solar máxima (oblicuidad de la eclíptica).
OBLICUIDAD_GRADOS = 23.44


def _elevacion_solar(lat: float, dia_del_anio: float, hora_utc: float,
                     lon: float) -> float:
    """Elevación del Sol (grados) para un instante dado (aprox. esférica).

    δ = oblicuidad·sin(2π·(N-80)/365) es la aproximación estándar de
    instituto (error <1°, suficiente para energía media anual).
    """
    decl = math.radians(
        OBLICUIDAD_GRADOS
        * math.sin(2.0 * math.pi * (dia_del_anio - 80.0) / 365.0))
    # Ángulo horario: 15°/hora respecto al mediodía solar local.
    h = math.radians(15.0 * (hora_utc + lon / 15.0 - 12.0))
    fi = math.radians(lat)
    sin_elev = (math.sin(fi) * math.sin(decl)
                + math.cos(fi) * math.cos(decl) * math.cos(h))
    return math.degrees(math.asin(max(-1.0, min(1.0, sin_elev))))


def datos_iluminacion_tierra(lat: float, lon: float) -> dict[str, Any]:
    """Iluminación terrestre con las mismas claves que `iluminacion.py`."""
    s0 = constantes.IRRADIANCIA_SOLAR_WM2

    horas_dia = 0
    energia_hora: list[float] = []
    for dia in range(1, 366):
        for hora in range(24):
            elev = _elevacion_solar(lat, dia, hora, lon)
            if elev > 0.0:
                horas_dia += 1
                energia_hora.append(
                    s0 * math.sin(math.radians(elev))
                    * TRANSMISION_ATMOSFERICA)
    total_horas = 365 * 24

    energia_media = (sum(energia_hora) / len(energia_hora)
                     if energia_hora else 0.0)
    polar = abs(lat) > 66.5
    nota_polar = (
        "por encima del círculo polar hay estaciones de sol continuo y de "
        "oscuridad continua: es el análogo terrestre del frío/extrema "
        "iluminación de los polos lunares"
        if polar else
        "cada punto gira al sol una vez por día (24 h): la fracción diurna "
        "anual es ~0.5 salvo en los polos")

    return {
        "fuente": "cálculo local (geometría solar estándar, 0 llamadas)",
        "fraccion_diurna_observada": round(horas_dia / total_horas, 3),
        "energia_solar": {
            "constante_solar_wm2": s0,
            "energia_media_estimada_wm2": round(energia_media, 1),
            "formula": ("E = S0 × sin(elevación) × "
                        f"{TRANSMISION_ATMOSFERICA} (promedio horario del año)"),
            "nota": ("la ATMÓSFERA es la diferencia clave con la Luna: "
                     "absorbe/difunde ~25 % de la luz con cielo claro y "
                     "mucho más con nubes; el dato lunar no tiene atmósfera"),
        },
        "variaciones_exposicion": {
            "nota": ("la oblicuidad (±23.44°) da las estaciones: la "
                     "elevación solar media oscila ±23° entre solsticios; "
                     "crúzalo con la variación estacional de POWER"),
        },
        "zonas_sombra_psr": {
            "nota": ("en la Tierra NO hay zonas de sombra permanente, pero "
                     "el análogo funcional son los inviernos polares "
                     "(meses sin sol): compara esta latitud con un PSR "
                     "lunar por duración de la oscuridad y temperatura"),
        },
        "nota_ciclo": nota_polar,
    }
