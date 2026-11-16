"""Iluminación — horas de luz, energía solar y zonas en sombra (PSR).

La iluminación NO se mide con un sensor: se CALCULA a partir de la geometría
Sol-cuerpo-superficie. Las fuentes del proyecto ya nos la dan casi lista:
  - Treks publica capas renderizadas de iluminación media (LOLA/Kaguya) y
    de regiones en sombra permanente (PSR): las sacamos del catálogo que
    `api.py` baja UNA vez (0 llamadas aquí).
  - Diviner registra el ángulo cenital solar de cada observación: con eso
    estimamos la fracción de tiempo con sol sobre el horizonte (también 0
    llamadas, reutiliza el CSV térmico).
  - La energía solar es un cálculo local: E = S0 × fracción iluminada.
"""

from __future__ import annotations

from typing import Any

from . import constantes, utilidades


# ---------------------------------------------------------------------------
# 1. Fracción de tiempo con Sol sobre el horizonte (reutiliza Diviner)
# ---------------------------------------------------------------------------

def fraccion_diurna(res_diviner: dict[str, Any] | None) -> float | None:
    """Proporción de observaciones de Diviner tomadas de día (csunzen < 90°).

    En una caja pequeña la sonda pasó pocas veces, así que es una MUESTRA, no
    un ciclo completo; sirve como indicio (0 = siempre en sombra, 1 = siempre
    al sol). Devuelve None si no hay CSV de Diviner o no trae el ángulo.
    """
    if not res_diviner:
        return None
    zen = res_diviner.get("_angulos_solares")  # lista de csunzen que api guarda
    if not zen:
        return None
    dias = sum(1 for z in zen if z < 90)
    return round(dias / len(zen), 3)


# ---------------------------------------------------------------------------
# 2. Energía solar recibida (cálculo local, sin llamadas)
# ---------------------------------------------------------------------------

def energia_solar_media_wm2(faccion_iluminada: float | None,
                            cuerpo: str = "moon") -> dict[str, Any]:
    """E ≈ S0 × fracción de superficie iluminada (sin atmósfera apreciable).

    S0 depende del cuerpo: 1361 W/m² a 1 UA (Luna/Tierra) y ≈586 W/m² en
    Marte (orbita a ~1.52 UA). Usar el valor terrestre para Marte inflaría
    la energía estimada 2.3 veces.
    """
    s0 = (constantes.IRRADIANCIA_SOLAR_MARTE_WM2 if cuerpo == "mars"
          else constantes.IRRADIANCIA_SOLAR_WM2)
    detalle: dict[str, Any] = {
        "constante_solar_wm2": s0,
        "formula": "E = S0 × fracción_iluminada",
    }
    if faccion_iluminada is not None:
        detalle["energia_media_estimada_wm2"] = round(s0 * faccion_iluminada, 1)
    else:
        detalle["nota"] = ("sin fracción iluminada; usa las capas de "
                           "iluminación de Treks para el mapa anual")
    return detalle


# ---------------------------------------------------------------------------
# 3. Sección completa de iluminación
# ---------------------------------------------------------------------------

def datos_iluminacion(capas: list[dict[str, Any]],
                      res_diviner: dict[str, Any] | None,
                      cuerpo: str = "moon") -> dict[str, Any]:
    """Capas de iluminación y PSR + fracción diurna + energía solar.

    `cuerpo` ajusta la constante solar (Marte recibe ~43 % de la que llega
    a la Luna/Tierra por estar más lejos del Sol).
    """
    pc = constantes.PALABRAS_CLAVE_CAPAS

    seccion: dict[str, Any] = {
        "fraccion_diurna_observada": fraccion_diurna(res_diviner),
        "capas_iluminacion": utilidades.capas_por_keyword(capas, pc["iluminacion"]),
        "variaciones_exposicion": {
            "nota": ("Las capas de iluminación media (LOLA/Kaguya) resumen "
                     "meses de geometría solar: % de tiempo iluminado por "
                     "píxel. Para la exposición a lo largo del año, cruza "
                     "esas capas con la fecha de las observaciones Diviner."),
        },
        "zonas_sombra_psr": {
            "capas": utilidades.capas_por_keyword(capas, pc["sombra"]),
            "nota": ("Los PSR (Permanently Shadowed Regions) son zonas donde "
                     "el Sol nunca supera el horizonte: allí el hielo de agua "
                     "sobrevive. Para saber si el punto cae DENTRO de un PSR, "
                     "muestrea la capa con rasterio o compruébalo en Moon "
                     "Trek; aquí damos las capas y, si hubo datos Diviner, "
                     "el indicio de fracción diurna."),
        },
        "energia_solar": energia_solar_media_wm2(
            fraccion_diurna(res_diviner), cuerpo),
    }
    return seccion
