"""termico_tierra.py — temperatura de superficie de la TIERRA con el MISMO
formato que la térmica lunar de Diviner (rama `tierra-datos-crudos`).

FUENTE PRINCIPAL (sin credenciales): NASA POWER (power.larc.nasa.gov), que
expone la 'Earth Skin Temperature' (TS) del modelo MERRA-2. API REST JSON
abierta: dos peticiones de ~2 s cada una y nada más que descargar:
  - /temporal/climatology/point  -> media mensual multi-año (12 valores)
  - /temporal/hourly/point       -> serie horaria del último año completo
    (8 760 valores, ~0.16 MB) para separar día y noche.

MÉTRICA HONESTA: TS de POWER es un REANÁLISIS (modelo asimilado, celda
~0.5°×0.625° ≈ 50 km), no una medida satelital como Diviner. Para un análogo
es lo comparable a Diviner (magnitud, ciclo día/noche y estacional), pero la
resolución es regional; la nota lo dice claro en la sección.

VÍA MEJORADA (requiere cuenta gratuita de Earthdata Login): MOD11A2 (MODIS
Terra LST, 1 km, medidas reales). Los granules están en rutas
'lp-prod-protected' y devuelven 401 sin credenciales (verificado). Las
credenciales van en .env (copiar .env.example -> .env y rellenar
EARTHDATA_USERNAME / EARTHDATA_PASSWORD). Queda como mejora futura.

CONVERSIÓN DE UNIDADES: POWER da °C; el colector trabaja en K como Diviner
(+273.15), para que el resumen del registro sea directamente comparable.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from . import utilidades

POWER = "https://power.larc.nasa.gov/api"


def _c_a_k(v: float) -> float:
    return round(float(v) + 273.15, 3)


def datos_termico_tierra(lat: float, lon: float,
                         aviso=None) -> dict[str, Any]:
    """Térmica terrestre con las mismas claves que `termico.datos_diviner`:
      'temperatura_superficial'  {n,min,max,media,mediana,desv_estandar} en K
      'dia_noche'                {media_dia_k, media_noche_k, diferencia_k}
      'variacion_estacional'     {media_por_mes_k, variacion_k, nota}
    """
    import requests

    def _aviso(msg: str) -> None:
        if aviso:
            aviso(msg)

    res: dict[str, Any] = {
        "fuente": "NASA POWER (MERRA-2, Earth Skin Temperature, TS)",
        "resolucion": "modelo de reanálisis, celda ~0.5°x0.625° (~50 km): "
                      "regional, no satelital",
    }
    try:
        # --- 1) climatología mensual (12 valores, multi-año) --------------
        _aviso("NASA POWER climatology (TS mensual)...")
        r = requests.get(f"{POWER}/temporal/climatology/point", params={
            "parameters": "TS", "community": "RE",
            "latitude": lat, "longitude": lon, "format": "JSON"}, timeout=120)
        r.raise_for_status()
        ts_mes = r.json()["properties"]["parameter"]["TS"]
        meses: dict[str, float] = {}
        for mes in ("JAN", "FEB", "MAR", "APR", "MAY", "JUN",
                    "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"):
            v = ts_mes.get(mes)
            if v is not None and v > -900:  # -999 = sin dato
                meses[mes] = float(v)
        if not meses:
            res["error"] = "POWER climatology no devolvió TS para este punto"
            return res

        # media anual oficial del propio POWER ('ANN') o media de los meses
        media_c = ts_mes.get("ANN")
        media_c = float(media_c) if media_c is not None and media_c > -900 \
            else sum(meses.values()) / len(meses)

        # --- 2) serie horaria del último año completo (día/noche) ---------
        anio = datetime.now().year - 1  # último año COMPLETO
        _aviso(f"NASA POWER hourly (TS, {anio}, 8760 valores)...")
        r = requests.get(f"{POWER}/temporal/hourly/point", params={
            "parameters": "TS", "community": "RE",
            "latitude": lat, "longitude": lon, "format": "JSON", "tz": "lst",
            "start": f"{anio}0101", "end": f"{anio}1231"}, timeout=300)
        r.raise_for_status()
        serie = r.json()["properties"]["parameter"]["TS"]
        horas = [(int(k[-2:]), float(v)) for k, v in serie.items()
                 if v is not None and v > -900]

        # --- 3) formato idéntico al de Diviner ----------------------------
        temp_c = [v for _h, v in horas] or list(meses.values())
        res["n_observaciones"] = len(horas) or len(meses)
        res["temperatura_superficial"] = utilidades.estadisticas(
            [_c_a_k(v) for v in temp_c])
        res["temperatura_superficial"]["unidad_nota"] = (
            "TS en K (POWER da °C; convertido) — media/anual del reanálisis")

        if len(horas) >= 48:
            dia = [v for h, v in horas if 6 <= h < 18]
            noche = [v for h, v in horas if h < 6 or h >= 18]
            if dia and noche:
                mdia = sum(dia) / len(dia)
                mnoche = sum(noche) / len(noche)
                res["dia_noche"] = {
                    "media_dia_k": _c_a_k(mdia),
                    "media_noche_k": _c_a_k(mnoche),
                    "diferencia_k": round(mdia - mnoche, 2),
                    "metodo": "horas locales (tz=lst) 6..17 = día; el resto "
                              "noche (serie horaria del año completo)",
                }
        if len(meses) >= 2:
            orden = ("JAN", "FEB", "MAR", "APR", "MAY", "JUN",
                     "JUL", "AUG", "SEP", "OCT", "NOV", "DEC")
            res["variacion_estacional"] = {
                "media_por_mes_k": {f"{i+1:02d}": _c_a_k(meses[m])
                                    for i, m in enumerate(orden)
                                    if m in meses},
                "variacion_k": round(max(meses.values()) - min(meses.values()),
                                     2),
                "nota": "climatología mensual multi-año de POWER (misma "
                        "lectura que el ciclo estacional de Diviner)",
            }
    except Exception as exc:
        res["error"] = f"NASA POWER falló: {exc}"
    return res
