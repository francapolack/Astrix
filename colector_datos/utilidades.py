"""Utilidades de cálculo y helpers HTTP.

Todo aquí es matemática "de instituto" (medias, desviaciones, distancias en
una esfera) para que un tercero pueda seguirlo sin saber de geoprocesamiento.
Estas funciones NO tocan la red: reciben datos ya descargados y devuelven
resultados. Así las fuentes (que sí hablan con las APIs) quedan separadas
del cálculo, que se puede probar sin conexión.
"""

from __future__ import annotations

import math
from typing import Any

from . import constantes


# ---------------------------------------------------------------------------
# Normalización de nombres y cajas de búsqueda (bounding boxes)
# ---------------------------------------------------------------------------

def normalizar_cuerpo(nombre: str) -> str:
    """Acepta 'luna'/'moon', 'marte'/'mars', 'tierra'/'earth' y devuelve el
    código interno que usan las APIs de nsac ('moon', 'mars', 'earth')."""
    n = (nombre or "").strip().lower()
    mapa = {"luna": "moon", "moon": "moon",
            "marte": "mars", "mars": "mars",
            "tierra": "earth", "earth": "earth"}
    if n not in mapa:
        raise ValueError(f"Cuerpo desconocido: {nombre!r}. Usa luna/marte/tierra.")
    return mapa[n]


def cajas_gds(lat: float, lon: float, radio: float) -> list[tuple[float, float, float, float]]:
    """Cajas (minlat, maxlat, oeste, este) para el GDS de PDS.

    El GDS trabaja SIEMPRE en el convenio de longitudes 0-360 y rechaza
    cualquier caja con longitud negativa (p.ej. un sitio en lon -23.7 daba
    'Invalid Lat/Lon Bounding Box'). Por eso aquí se convierte TODO a 0-360:
    una longitud de -23.7 pasa a ser 336.3 y el GDS la acepta.

    Si la caja convertida cruza el 360 (que es el mismo meridiano 0;
    p.ej. lon 0.05 con radio 0.1 → 359.95..360.15), se parte en dos mitades:
    [oeste..360] y [0..este]. Devuelve una LISTA porque puede haber una o
    dos cajas; el llamador consulta cada una y junta los resultados.
    Los módulos que leen los CSV ya normalizan las longitudes a [-180, 180].
    Latitudes se recortan al rango [-90, 90].
    """
    lat_sur = max(-90.0, lat - radio)
    lat_norte = min(90.0, lat + radio)
    oeste = (lon - radio) % 360.0
    este = (lon + radio) % 360.0

    if oeste <= este:
        return [(lat_sur, lat_norte, oeste, este)]
    # La caja cruza el 360 (el meridiano 0 en el convenio [-180, 180]).
    return [(lat_sur, lat_norte, oeste, 360.0),
            (lat_sur, lat_norte, 0.0, este)]


def caja_stac(lat: float, lon: float, radio: float) -> tuple[float, float, float, float]:
    """Caja (oeste, sur, este, norte) para STAC (USGS, Copernicus) y CMR.

    ¡Distinto orden que el GDS! STAC/CMR quieren (oeste, sur, este, norte).
    """
    return (lon - radio, lat - radio, lon + radio, lat + radio)


# ---------------------------------------------------------------------------
# Estadísticas sencillas sobre listas de números
# ---------------------------------------------------------------------------

def estadisticas(valores: list[float]) -> dict[str, Any] | None:
    """Min, max, media, mediana y desviación estándar de una lista de valores.

    Filtra los NaN (un NaN nunca es igual a sí mismo: eso es lo que comprueba
    `x == x`). Devuelve None si no queda ningún valor válido. Todos los
    números se redondean a 3 decimales para que el diccionario sea legible.
    """
    v = sorted(float(x) for x in valores if x == x)  # x == x es False para NaN
    if not v:
        return None
    n = len(v)
    media = sum(v) / n
    desv = math.sqrt(sum((x - media) ** 2 for x in v) / n) if n > 1 else 0.0
    return {
        "n": n,
        "min": round(v[0], 3),
        "max": round(v[-1], 3),
        "media": round(media, 3),
        "mediana": round(v[n // 2], 3),
        "desv_estandar": round(desv, 3),
    }


# ---------------------------------------------------------------------------
# Geometría en una esfera (distancias y pendientes)
# ---------------------------------------------------------------------------

def distancia_gran_circulo(lat1: float, lon1: float,
                           lat2: float, lon2: float, radio_m: float) -> float:
    """Distancia entre dos puntos de un cuerpo esférico (fórmula de haversine).

    `radio_m` es el radio del cuerpo en metros (Luna 1 737 400, Marte 3 396 190).
    """
    fi1, fi2 = math.radians(lat1), math.radians(lat2)
    dfi = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dfi / 2) ** 2
         + math.cos(fi1) * math.cos(fi2) * math.sin(dlon / 2) ** 2)
    # clamp de seguridad por errores de redondeo del punto flotante
    a = min(1.0, max(0.0, a))
    return 2 * radio_m * math.asin(math.sqrt(a))


def proyeccion_local(lat0: float, lon0: float, lat: float, lon: float,
                     radio_m: float) -> tuple[float, float]:
    """Convierte (lat, lon) a metros locales (este, norte) respecto al centro.

    Es la proyección plana "de vecinos": x = R·cos(lat0)·Δlon, y = R·Δlat.
    Es válida para cajas pequeñas (radio de <1°) y resuelve el problema de
    los polos, donde 1° de longitud son centímetros y los cálculos en grados
    se degradan. Δlon se ajusta al rango [-180, 180] para que el salto
    359.9°→0.1° cuente como 0.2° y no como 359.8°.
    """
    dlon = ((lon - lon0 + 180.0) % 360.0) - 180.0
    x = math.radians(dlon) * radio_m * math.cos(math.radians(lat0))
    y = math.radians(lat - lat0) * radio_m
    return x, y


def _agrupar_en_celdas(puntos: list[dict[str, float]], celda_m: float) -> dict[tuple[int, int], list[dict]]:
    """Reparte los puntos en celdas de una cuadrícula de `celda_m` metros.

    Los puntos DEBEN llevar ya sus coordenadas locales 'x' e 'y' (en metros,
    de `proyeccion_local`). Cada uno cae en la celda (fila, columna) según
    floor(x/celda) y floor(y/celda). Devuelve un dict celda -> puntos.
    """
    celdas: dict[tuple[int, int], list[dict]] = {}
    for p in puntos:
        fila = int(math.floor(p["y"] / celda_m))
        col = int(math.floor(p["x"] / celda_m))
        celdas.setdefault((fila, col), []).append(p)
    return celdas


def _resumen_por_celda(puntos, celda_m):
    """Media y desviación típica de la elevación por celda (paso común de
    pendiente_y_rugosidad y detectar_crateres)."""
    resumenes = []
    for (fila, col), grupo in _agrupar_en_celdas(puntos, celda_m).items():
        radios = [p["radio_m"] for p in grupo]
        n = len(radios)
        media = sum(radios) / n
        desv = math.sqrt(sum((r - media) ** 2 for r in radios) / n) if n > 1 else 0.0
        resumenes.append({
            "fila": fila,                    # posición en la cuadrícula:
            "col": col,                      # permite buscar vecinos sin
            "x": (col + 0.5) * celda_m,      # comparar todas contra todas
            "y": (fila + 0.5) * celda_m,
            "media_m": media,
            "desv_m": desv,
            "n": n,
        })
    return resumenes


def _vecindario(indice: dict[tuple[int, int], dict], celda: dict,
                alcance: int) -> list[tuple[dict, float, int, int]]:
    """Vecinos de UNA celda mirando solo el cuadrado ±`alcance` de la rejilla.

    Antes se comparaban TODAS las celdas contra todas (O(n²)): con cajas
    grandes eso son miles de millones de operaciones y el programa parecía
    colgado durante horas. Como las celdas viven en una cuadrícula regular
    de lado `celda_m`, ningún vecino cercano puede caer fuera del cuadrado
    de ±alcance: basta con mirar ahí.

    Devuelve (celda_vecina, distancia_m, df, dc) sin contar la propia celda.
    """
    vecinos: list[tuple[dict, float, int, int]] = []
    f0, c0 = celda["fila"], celda["col"]
    for df in range(-alcance, alcance + 1):
        for dc in range(-alcance, alcance + 1):
            if df == 0 and dc == 0:
                continue
            otra = indice.get((f0 + df, c0 + dc))
            if otra is not None:
                d = math.hypot(otra["x"] - celda["x"], otra["y"] - celda["y"])
                vecinos.append((otra, d, df, dc))
    return vecinos


def _con_coordenadas_locales(puntos, radio_cuerpo_m):
    """Devuelve una copia de los puntos con 'x'/'y' locales en metros,
    usando como centro el promedio de todos los puntos (para que ninguna
    coordenada crezca más allá del tamaño de la caja)."""
    lat0 = sum(p["lat"] for p in puntos) / len(puntos)
    lon0 = sum(p["lon"] for p in puntos) / len(puntos)
    out = []
    for p in puntos:
        q = dict(p)
        q["x"], q["y"] = proyeccion_local(lat0, lon0, p["lat"], p["lon"],
                                          radio_cuerpo_m)
        out.append(q)
    return out, (lat0, lon0)


def pendiente_y_rugosidad(puntos: list[dict[str, float]],
                          radio_cuerpo_m: float,
                          celda_m: float = 100.0,
                          distancia_max_m: float = 1000.0) -> dict[str, Any]:
    """Pendiente y rugosidad a partir de una nube de puntos de elevación.

    Método (simple y auditable):
      1. Los puntos se proyectan a metros locales y se agrupan en celdas de
         `celda_m` metros de lado.
      2. RUGOSIDAD = desviación típica de la elevación DENTRO de cada celda
         (terreno liso ≈ 0; pedregoso/ondulado ≫ 0).
      3. PENDIENTE = atan2(Δh, d) entre pares de celdas separadas menos de
         `distancia_max_m`, en grados.

    Funciona con LOS PUNTOS que ya trajimos del GDS: cero llamadas HTTP extra.
    """
    if len(puntos) < 10:
        return {"nota": f"insuficientes puntos ({len(puntos)}) para estimar "
                        "pendiente/rugosidad; usa el DTM de USGS STAC",
                "n_puntos": len(puntos)}

    puntos, _centro = _con_coordenadas_locales(puntos, radio_cuerpo_m)
    celdas = _resumen_por_celda(puntos, celda_m)
    indice = {(c["fila"], c["col"]): c for c in celdas}
    # Cuántas celdas de rejilla equivalen a la distancia máxima de búsqueda.
    alcance = int(math.ceil(distancia_max_m / celda_m))

    # Rugosidad: solo celdas con >=3 puntos (una medida aislada no define
    # "variación").
    rugosidades = [c["desv_m"] for c in celdas if c["n"] >= 3]

    # Pendiente: pares de celdas cercanas. Cada par se cuenta UNA vez
    # (solo "medio plano": df>0, o df==0 y dc>0), porque la pendiente entre
    # a y b es la misma que entre b y a.
    pendientes = []
    for c in celdas:
        for otra, d, df, dc in _vecindario(indice, c, alcance):
            if d > distancia_max_m:
                continue
            if df < 0 or (df == 0 and dc <= 0):
                continue
            pendientes.append(math.degrees(
                math.atan2(abs(c["media_m"] - otra["media_m"]), d)))

    return {
        "metodo": (f"celdas de {celda_m:.0f} m en proyección local; "
                   "rugosidad = desviación típica dentro de celda; "
                   "pendiente = atan2(Δh, d) entre celdas a menos de "
                   f"{distancia_max_m:.0f} m (búsqueda por rejilla)"),
        "n_puntos": len(puntos),
        "n_celdas": len(celdas),
        "rugosidad_m": util_estad(rugosidades),
        "pendiente_grados": util_estad(pendientes),
    }


def util_estad(valores: list[float]) -> dict[str, float] | None:
    """Atajo: versión redondeada de `estadisticas` para listas internas."""
    return estadisticas(valores)


def detectar_crateres(puntos: list[dict[str, float]],
                      radio_cuerpo_m: float,
                      celda_m: float = 100.0,
                      radio_busqueda_m: float = 500.0,
                      sigma: float = 1.5) -> dict[str, Any]:
    """Detección APROXIMADA de cráteres sobre la nube de puntos.

    Idea: un cráter es una depresión. Buscamos celdas cuyo nivel medio esté
    claramente por debajo (más de `sigma` desviaciones) del nivel medio de
    las celdas situadas a menos de `radio_busqueda_m`. Cada una es un
    "candidato a cráter" con su profundidad estimada.

    Es una heurística de cribado (los cráteres confirmados se verifican con
    el DTM de alta resolución o el mapa geológico), pero sale GRATIS de los
    mismos puntos LOLA: cero llamadas HTTP extra. Con pocos puntos o cajas
    muy pequeñas puede no encontrar nada: es normal.
    """
    if len(puntos) < 30:
        return {"nota": f"insuficientes puntos ({len(puntos)}) para detectar "
                        "cráteres; usa el DTM de USGS STAC",
                "candidatos": []}

    puntos, (lat0, lon0) = _con_coordenadas_locales(puntos, radio_cuerpo_m)
    celdas = _resumen_por_celda(puntos, celda_m)
    if len(celdas) < 9:
        return {"nota": "la caja es demasiado pequeña para esta resolución",
                "candidatos": []}

    indice = {(c["fila"], c["col"]): c for c in celdas}
    alcance = int(math.ceil(radio_busqueda_m / celda_m))

    global_media = sum(c["media_m"] for c in celdas) / len(celdas)
    global_desv = math.sqrt(
        sum((c["media_m"] - global_media) ** 2 for c in celdas) / len(celdas))

    # Para pasar las celdas a lat/lon en el resultado necesitamos el centro
    # de proyección: invertimos proyeccion_local con la inversa plana.
    def _a_latlon(x, y):
        lat = lat0 + math.degrees(y / radio_cuerpo_m)
        lon = lon0 + math.degrees(
            x / (radio_cuerpo_m * math.cos(math.radians(lat0))))
        return lat, ((lon + 180.0) % 360.0) - 180.0

    candidatos = []
    for c in celdas:
        vecinos = [
            otra["media_m"]
            for otra, d, _df, _dc in _vecindario(indice, c, alcance)
            if d <= radio_busqueda_m
        ]
        if len(vecinos) < 4:
            continue
        media_vecinos = sum(vecinos) / len(vecinos)
        hundimiento = media_vecinos - c["media_m"]
        if global_desv > 0 and hundimiento > sigma * global_desv:
            lat, lon = _a_latlon(c["x"], c["y"])
            candidatos.append({
                "lat": round(lat, 5),
                "lon": round(lon, 5),
                "profundidad_est_m": round(hundimiento, 1),
            })

    candidatos.sort(key=lambda c: c["profundidad_est_m"], reverse=True)
    return {
        "metodo": (f"depresiones de >{sigma}σ respecto a las celdas a menos "
                   f"de {radio_busqueda_m:.0f} m (celdas de {celda_m:.0f} m) "
                   "sobre la nube de puntos"),
        "n_candidatos": len(candidatos),
        "candidatos": candidatos[:10],  # los 10 más profundos
    }


# ---------------------------------------------------------------------------
# Búsqueda de capas Treks (ya descargadas) y plantillas de teselas
# ---------------------------------------------------------------------------

def capas_por_keyword(capas: list[dict[str, Any]], palabras: list[str],
                      limite: int = 8) -> list[dict[str, Any]]:
    """Filtra el catálogo de Treks (ya en memoria) por palabras clave.

    No gasta llamadas HTTP: el catálogo se baja una única vez con
    `trek.layers(...)` y aquí solo se recorre la lista. Coincide si la palabra
    aparece en el id o en el título de la capa.
    """
    encontradas = []
    for capa in capas:
        id_ = (capa.get("id") or "").lower()
        titulo = (capa.get("title") or "").lower()
        if any(p in id_ or p in titulo for p in palabras):
            encontradas.append({
                "id": capa.get("id"),
                "titulo": capa.get("title"),
                "mision": capa.get("mission"),
                "resolucion": capa.get("resolution"),
                "bbox": capa.get("bbox"),
            })
            if len(encontradas) >= limite:
                break
    return encontradas


def urls_de_tesela(cuerpo: str, capas: list[dict[str, Any]],
                   grupos: dict[str, list[str]], max_por_grupo: int = 1) -> dict[str, list[dict]]:
    """URLs de teselas WMTS listas para Leaflet/MapLibre.

    Para cada grupo de parámetros (p.ej. 'pendiente': ['slope']) toma la
    primera capa que coincida, pregunta su servicio WMTS y construye la
    plantilla de URL con {z}/{row}/{col}. Son 2 llamadas HTTP por capa
    (servicios + GetCapabilities), por eso esta función es OPCIONAL: para la
    app visual vale la pena, para el análisis de datos no.
    """
    from nsac.sources import trek  # import tardío: evita dependencia circular

    urls: dict[str, list[dict]] = {}
    for nombre_parametro, palabras in grupos.items():
        coincidentes = [c for c in capas
                        if any(p in (c.get("id") or "").lower()
                               or p in (c.get("title") or "").lower()
                               for p in palabras)]
        for capa in coincidentes[:max_por_grupo]:
            uuid = capa.get("uuid")
            ident = capa.get("id")
            try:
                servicios = trek.layer_services(cuerpo, uuid)
                if not servicios:
                    continue
                endpoint = servicios[0]["endPoint"]
                plantilla = trek.tile_template(cuerpo, ident, endpoint)
                urls.setdefault(nombre_parametro, []).append({
                    "capa": ident,
                    "url_teselas": plantilla["url_template"],
                })
            except Exception as exc:  # una capa que falla no rompe las demás
                urls.setdefault(nombre_parametro, []).append(
                    {"capa": ident, "error": str(exc)})
    return urls


# ---------------------------------------------------------------------------
# Buscador de columnas en los CSV que devuelve el GDS
# ---------------------------------------------------------------------------

def columna_con(df, fragmentos: list[str]):
    """Primera columna del DataFrame cuyo nombre contiene algún fragmento.

    El GDS nombra las columnas distinto según el dataset (LOLA usa
    'D1_Latitude', Diviner usa 'clat'...). Con esta función buscamos por
    'significado' en vez de por nombre exacto y el código no se rompe si
    cambian los detalles.
    """
    for col in df.columns:
        nombre = str(col).lower()
        if any(f in nombre for f in fragmentos):
            return col
    return None
