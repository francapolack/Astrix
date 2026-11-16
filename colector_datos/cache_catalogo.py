"""cache_catalogo.py — caché local de CATÁLOGOS (Treks, STAC).

El catálogo de Solar System Treks (~8 s) y la búsqueda STAC de USGS (~2-3 s)
son consultas de red que repetimos en casi cada consulta. Sus respuestas son
CATÁLOGOS: listas de capas/productos que no cambian entre una llamada y otra
del mismo día (mucho menos entre una llamada y otra del hackathon).

Con esta caché una consulta "tibia" deja de depender de 3 servidores: solo
quedan en red las fuentes de DATOS (Diviner/LOLA vía GDS, o el tile DTM si no
está en disco). Medido: tibio 11 s → ~3 s (ver NOTAS_NOCTURNAS.md).

Diseño (mismo espíritu que cache_gds.py):
  - Cada catálogo se guarda como JSON en colector_datos/data/cache/catalogos/
    con una marca de fecha. La carpeta queda excluida del repo por la regla
    'data/' del .gitignore.
  - ttl_horas=None (por defecto) = sin caducidad: para la demo en vivo es lo
    más seguro (si la NASA está lenta, el catálogo sale del disco igual).
    Si algún día se quiere frescura, basta pasar ttl_horas=24.
  - Si el archivo está corrupto o el TTL venció, se consulta la red y se
    re-escribe. Si escribir falla (permisos/disco), la consulta sigue:
    la caché es un extra, nunca un requisito.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any, Callable

from . import constantes

CARPETA = constantes.RUTA_REGISTRO.parent / "cache" / "catalogos"


def json_o_red(nombre: str, productor: Callable[[], Any],
               ttl_horas: float | None = None) -> tuple[Any, bool]:
    """Devuelve (dato, vino_de_cache) para UN catálogo.

    nombre    nombre legible de la entrada (p.ej. 'treks_moon_eq').
    productor función sin argumentos que devuelve el dato de la red
              (p.ej. lambda: trek.layers("moon", projtype="eq")).
    ttl_horas vida máxima del caché; None = sin caducidad.

    El 'productor' se ejecuta SOLO si no hay caché válida; si falla, el
    error sube al llamador (igual que si no hubiera caché).
    """
    ruta = CARPETA / f"{nombre}.json"

    # --- 1) ¿hay caché válida? -------------------------------------------
    if ruta.exists():
        try:
            doc = json.loads(ruta.read_text(encoding="utf-8"))
            edad_s = time.time() - float(doc.get("_fecha_epoch", 0))
            if ttl_horas is None or edad_s < ttl_horas * 3600:
                return doc.get("dato"), True
            # TTL vencido: seguimos a la red (y se reescribe abajo).
        except Exception:
            pass  # JSON corrupto: se re-baja de la fuente

    # --- 2) red + guardado (el error del productor sube al llamador) ------
    dato = productor()
    try:
        CARPETA.mkdir(parents=True, exist_ok=True)
        doc = {
            "_fecha_epoch": time.time(),
            "_fecha_iso": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "_ttl_horas": ttl_horas,
            "dato": dato,
        }
        # Escritura atómica simple: temporal con PID + reemplazo.
        temporal = ruta.with_suffix(f".{os.getpid()}.tmp")
        temporal.write_text(json.dumps(doc, ensure_ascii=False),
                            encoding="utf-8")
        os.replace(temporal, ruta)
    except Exception:
        pass  # sin disco: la consulta sigue siendo válida
    return dato, False
