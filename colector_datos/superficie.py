"""Superficie — tipo de roca, minerales, reflectancia/albedo y polvo.

El albedo/reflectancia REAL viene del mismo CSV de Diviner que descarga
`termico.datos_diviner` (canales 1-2 solares): aquí solo lo recibimos,
clasificamos el tipo de roca con una heurística documentada y añadimos las
fuentes de mineralogía:
  - capas del catálogo Treks ya bajadas (Fe, Ti, Th, composición): 0 llamadas.
  - UNA búsqueda PDS de bundles Clementine (1 llamada HTTP en total).
"""

from __future__ import annotations

from typing import Any

from . import constantes, utilidades


# ---------------------------------------------------------------------------
# 1. Clasificación de roca a partir del albedo (heurística simple)
# ---------------------------------------------------------------------------

def clasificar_roca_lunar(albedo: float | None) -> dict[str, Any] | None:
    """Aproxima el tipo de terreno lunar a partir de la reflectancia media.

    Regla básica de selenografía (es una HEURÍSTICA, no una medición):
      - reflectancia alta (> 0.32) -> tierras altas: anortosita, feldespato
        cálcico, terrenos antiguos y claros.
      - reflectancia baja (< 0.22) -> mares: basalto (lava solidificada).
      - valores intermedios        -> regolito mixto / bordes de mares.
    """
    if albedo is None:
        return None
    if albedo > 0.32:
        clase = "tierras altas — anortosita (feldespato cálcico, terreno claro)"
    elif albedo < 0.22:
        clase = "mares — basalto (terreno volcánico oscuro)"
    else:
        clase = "transición — regolito mixto (anortosita + basalto)"
    return {
        "clasificacion": clase,
        "metodo": "umbral sobre la reflectancia media de Diviner (heurística; "
                  "confírmalo con las capas de FeO/TiO2 de Clementine)",
    }


# ---------------------------------------------------------------------------
# 2. Bundles PDS de mineralogía (1 llamada en total)
# ---------------------------------------------------------------------------

def bundles_minerales() -> list[dict[str, Any]]:
    """Busca en el catálogo PDS4 los bundles de Clementine (FeO/TiO2/albedo).

    Es UNA llamada al PDS Search API (el API no filtra por texto de forma
    fiable, así que `search_bundles` baja el catálogo y filtra en local).
    Devuelve id, título y URL de la etiqueta PDS4 de cada bundle.
    """
    from nsac.sources import pds

    try:
        bundles = pds.search_bundles(constantes.BUSQUEDA_PDS_MINERALES)
        return [
            {
                "lidvid": b.get("lidvid"),
                "titulo": b.get("title"),
                "url_etiqueta": b.get("label_url"),
            }
            for b in bundles[:8]  # los 8 primeros bastan como puntero
        ]
    except Exception as exc:
        return [{"error": f"PDS Search no respondió: {exc}"}]


# ---------------------------------------------------------------------------
# 3. Sección completa de superficie
# ---------------------------------------------------------------------------

def datos_superficie(res_diviner: dict[str, Any] | None,
                     capas: list[dict[str, Any]],
                     cuerpo: str = "moon") -> dict[str, Any]:
    """Une albedo (Diviner), minerales (Treks + PDS) y polvo/regolito.

    `res_diviner` es lo que devuelve `termico.datos_diviner(...)`: de ahí
    cogemos 'reflectancia_albedo' sin gastar ni una llamada más.
    `capas` es el catálogo de Treks ya en memoria.
    `cuerpo`: en Marte NO se consultan los bundles de Clementine (es una
    sonda LUNAR; los mapas mineralógicos marcianos son CRISM/OMEGA/TES).
    """
    res_diviner = res_diviner or {}
    pc = constantes.PALABRAS_CLAVE_CAPAS

    # --- reflectancia / albedo --------------------------------------------
    refl = res_diviner.get("reflectancia_albedo")
    if not refl:
        refl = {"nota": "sin datos de Diviner: usa las capas 'albedo' de Treks "
                        "o el STAC para descargar reflectancia"}

    seccion: dict[str, Any] = {
        "reflectancia_albedo": refl,
        "tipo_roca": clasificar_roca_lunar(
            refl.get("media") if isinstance(refl, dict) else None),
    }

    # --- minerales predominantes -------------------------------------------
    if cuerpo == "mars":
        seccion["minerales_predominantes"] = {
            "capas_trek": utilidades.capas_por_keyword(capas, pc["minerales"]),
            "bundles_pds": [],   # Clementine/LP son lunares: no aplica
            "nota": ("Los mapas mineralógicos marcianos salen de CRISM "
                     "(MRO), OMEGA (MEX) y TES (MGS): se eligen por las "
                     "capas de Mars Trek de arriba; para PDS busca los "
                     "bundles mro-m-cris o mex-m-omega."),
        }
    else:
        seccion["minerales_predominantes"] = {
            "capas_trek": utilidades.capas_por_keyword(capas, pc["minerales"]),
            "bundles_pds": bundles_minerales(),
            "nota": ("Clementine UVVIS: albedo y abundancia relativa de "
                     "Fe/Ti. Lunar Prospector: Th, K, Fe. Ambos están "
                     "indexados en PDS y varios mapas aparecen como capas "
                     "de Treks."),
        }

    # --- materiales superficiales y depósitos de polvo ----------------------
    if cuerpo == "mars":
        nota_polvo = ("Los depósitos de polvo marciano se mapean con TES/"
                      "THEMIS (capas de Mars Trek): el índice de recubrimiento "
                      "de polvo separa rocas recién barridas de zonas "
                      "empolvadas, clave para rodar sin atascarse.")
    else:
        nota_polvo = ("Toda la superficie lunar está cubierta de regolito "
                      "(polvo de impacto); los mapas de parámetro H (Lucey) "
                      "cuantifican su 'madurez'.")
    seccion["materiales_y_polvo"] = {
        "capas_trek": utilidades.capas_por_keyword(capas, pc["polvo"]),
        "nota": nota_polvo,
    }

    return seccion
