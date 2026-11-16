"""cache_gds.py — caché local de los CSV que genera el GDS de PDS.

El GDS fabrica los CSV a mano alzada en el servidor cada vez que se le
pregunta (por eso tarda minutos y a veces corta la conexión). PERO los datos
que entrega son HISTÓRICOS: las mediciones de LOLA/Diviner no cambian nunca.
Eso permite guardar el CSV la primera vez y reutilizarlo para siempre.

Esta caché es la garantía de la demo en vivo: si la NASA está lenta el día
de la presentación, cualquier sitio ya consultado responde en milisegundos
desde el disco.

Diseño:
  - La clave de caché es (query, caja redondeada a 4 decimales, extra). El
    redondeo evita que el ruido de punto flotante (2.0000000001 vs 2.0)
    duplique entradas.
  - El archivo se guarda con un nombre LEGIBLE en colector_datos/data/cache/
    (que el .gitignore ya excluye: son descargas, no código).
  - Sin caducidad: las mediciones orbitales no se reescriben. Si algún día
    quisiera invalidarse, basta con borrar la carpeta cache/.
"""

from __future__ import annotations

import hashlib
from typing import Any

import pandas as pd

from . import constantes

CARPETA = constantes.RUTA_REGISTRO.parent / "cache"


def _ruta_de_cache(query: str, caja: tuple[float, float, float, float],
                   extra: dict[str, Any]) -> Any:
    """Nombre de archivo legible y determinista para una consulta GDS.

    Ej: divinerrdr_m23p45_m23p35_157p75_157p85_fffffffff.csv
    ('m' = negativo, 'p' = punto decimal: seguro en Windows y en Git).
    """
    minlat, maxlat, oeste, este = (round(v, 4) for v in caja)

    def limpio(v: float) -> str:
        return f"{v:.4f}".replace("-", "m").replace(".", "p")

    partes = [query, limpio(minlat), limpio(maxlat),
              limpio(oeste), limpio(este)]
    if extra:
        # Los parámetros extra (p.ej. los canales de Diviner) van como una
        # huella corta al final, para no distinguir a simple vista igual.
        huella = hashlib.md5(
            repr(sorted(extra.items())).encode("utf-8")).hexdigest()[:8]
        partes.append(huella)
    return CARPETA / ("_".join(partes) + ".csv")


def leer_o_descargar(query: str, caja: tuple[float, float, float, float],
                     **extra: Any):
    """Devuelve (DataFrame, ruta, vino_de_cache) de UNA consulta GDS.

    Si ya bajamos esta caja antes, lee el CSV local (instantáneo). Si no,
    hace la consulta real al GDS y guarda el resultado para la próxima.
    Nunca lanza error de escritura: si no se puede cachear, se devuelve
    igualmente el DataFrame fresco (la caché es un extra, no un requisito).
    """
    from nsac.sources import pds

    ruta = _ruta_de_cache(query, caja, extra)
    if ruta.exists():
        try:
            df = pd.read_csv(ruta)
            df.columns = [str(c).strip() for c in df.columns]
            return df, ruta, True
        except Exception:
            pass  # caché corrupta: se re-baja de la fuente

    df = pds.gds_extract_points(query, caja, **extra)
    try:
        CARPETA.mkdir(parents=True, exist_ok=True)
        df.to_csv(ruta, index=False)
    except Exception:
        pass  # sin disco/escribir: la consulta sigue siendo válida
    return df, ruta, False
