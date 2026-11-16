"""NSAC — Colector de datos de sitio (Luna / Marte / Tierra análoga).

Objetivo de este paquete: UNA sola función que, al llamarla, devuelva un
diccionario de Python con TODOS los parámetros del reto:

    from colector_datos import obtener_datos_sitio

    datos = obtener_datos_sitio(cuerpo="luna", lat=-89.9, lon=0.05, radio=0.05)
    print(datos["topografia"]["elevacion_m"])

Parámetros cubiertos y su fuente (todo desde las fuentes del proyecto `nsac`):

    topografía  -> PDS GDS (LOLA) + USGS STAC (DTM Kaguya/HiRISE) + Treks
    térmica     -> PDS GDS (Diviner, 9 canales en UNA consulta)
    superficie  -> Diviner canales solares + PDS (Clementine) + Treks
    iluminación -> capas de Treks + Diviner (ángulo solar) + cálculo local

Módulos del paquete (uno por tema, para que sea fácil de entender):

    constantes.py       constantes físicas, sitios de ejemplo y palabras clave
    utilidades.py       cálculos (pendiente, rugosidad, cráteres, estadísticas)
    topografia.py       elevación, pendiente, rugosidad, cráteres/formaciones
    termico.py          temperatura media/max/min, día-noche, estacional
    superficie.py       tipo de roca, minerales, albedo, polvo/regolito
    iluminacion.py      horas de luz, energía solar, zonas en sombra (PSR)
    analogos_tierra.py  los mismos parámetros para un sitio TERRESTRE (CMR/GIBS)
    api.py              la función principal que une todo en un solo dict
    ejemplo_uso.py      script ejecutable de muestra
"""

import sys
from pathlib import Path

# Permitir importar `nsac` aunque este paquete se importe desde cualquier
# carpeta: añadimos la raíz del proyecto al path si no está ya.
_raiz = Path(__file__).resolve().parents[1]
if str(_raiz) not in sys.path:
    sys.path.insert(0, str(_raiz))

from .api import obtener_datos_sitio
from .analogos_tierra import datos_tierra

__all__ = ["obtener_datos_sitio", "datos_tierra"]
