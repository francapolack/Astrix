"""prueba_tierra.py — prueba el parámetro `incluir_tierra=True`.

Ejecútalo desde la raíz del proyecto:

    python -m colector_datos.prueba_tierra            # rápido (sin GDS, ~segundos)
    python -m colector_datos.prueba_tierra --completo # incluye también los GDS lunares

¿Qué estamos probando? El parámetro booleano `incluir_tierra` de
`obtener_datos_sitio(...)`. Cuando vale True, el diccionario resultante lleva
una sección EXTRA, `datos["analogos_tierra"]`, con el "lado Tierra" de la
comparación: qué datasets TERRESTRES cubren las mismas variables (elevación,
temperatura, albedo, humedad) para poder puntuar sitios de la Tierra con la
misma vara con la que puntuamos el sitio lunar/marciano.

La sección terrestre no descarga rásteres: devuelve el CATÁLOGO (nombres,
ids y URLs), porque la descarga real necesita cuenta gratuita de Earthdata.
Con los `concept_id` que devuelve, la app puede pedir granules después
(mirar el ejemplo del final del informe impreso).
"""

from __future__ import annotations

import argparse

from . import constantes
from .analogos_tierra import datos_tierra
from .api import obtener_datos_sitio


# ---------------------------------------------------------------------------
# Utilidades de impresión (mismo estilo que prueba_funcion.py)
# ---------------------------------------------------------------------------

def barra(titulo: str) -> None:
    """Separador de sección legible."""
    print("\n" + "=" * 72)
    print(f"  {titulo}")
    print("=" * 72)


def mostrar_colecciones(nombre_variable: str, entradas) -> None:
    """Imprime el bloque de UNA variable terrestre (elevación, temperatura...).

    `entradas` es lo que devuelve el catálogo CMR para esa variable: una
    lista de colecciones (nombre corto, título, concept_id) o un dict con
    'error' si la búsqueda falló. La función tolera ambos casos.
    """
    print(f"\n  · {nombre_variable.upper().replace('_', ' ')}")
    if not isinstance(entradas, list):
        print(f"    {entradas}")
        return
    if not entradas:
        print("    (CMR no devolvió colecciones para esta palabra clave)")
        return
    for c in entradas[:3]:  # las 3 primeras bastan para elegir
        print(f"    - {c.get('nombre_corto')}")
        print(f"      título     : {c.get('titulo')}")
        print(f"      concept_id : {c.get('concept_id')}")
        print(f"      cobertura  : {c.get('cobertura_temporal')}")


def mostrar_tierra(seccion: dict, lat: float, lon: float) -> None:
    """Sección completa `datos['analogos_tierra']` traducida a informe."""
    print(f"\n  Centro de la búsqueda terrestre: lat {lat}, lon {lon}")
    print(f"  {seccion.get('nota', '')}")

    # --- las 4 variables del catálogo CMR ----------------------------------
    for variable in ("elevacion", "temperatura_superficial",
                     "albedo_reflectancia", "humedad_suelo"):
        mostrar_colecciones(variable, seccion.get(variable))

    # --- capas GIBS para el visor -------------------------------------------
    print("\n  · TESELAS GIBS (imágenes listas para Leaflet/MapLibre)")
    gibs = seccion.get("teselas_gibs")
    if isinstance(gibs, list):
        for capa in gibs:
            print(f"    - {capa.get('id')}")
            print(f"      título: {capa.get('titulo')}  formato: {capa.get('formato')}")
        print("    cómo leerlo: son las mismas capas de Worldview; para el")
        print("    visor de la app se pegan como L.tileLayer sin más pasos.")
    else:
        print(f"    {gibs}")

    # --- Sentinel-2 (Copernicus) --------------------------------------------
    print("\n  · SENTINEL-2 SOBRE EL PUNTO (óptico de alta resolución)")
    s2 = seccion.get("sentinel2")
    if isinstance(s2, list) and s2:
        for e in s2:
            print(f"    - {e.get('id')}")
            print(f"      fecha: {e.get('fecha')}  nubes: {e.get('nubes_pct')}%")
    else:
        print(f"    {s2}")
    print("    cómo leerlo: son escenas de la ESA; comparar la textura del")
    print("    terreno terrestre con las capas de Moon/Mars Trek es directo.")


# ---------------------------------------------------------------------------
# Programa principal
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Prueba el parámetro incluir_tierra de obtener_datos_sitio.")
    parser.add_argument("--sitio", default="shackleton",
                        choices=list(constantes.SITIOS),
                        help="sitio lunar/marciano de partida")
    parser.add_argument("--completo", action="store_true",
                        help="incluye también las consultas GDS (tardan minutos)")
    args = parser.parse_args()

    sitio = constantes.SITIOS[args.sitio]

    print("\n" + "#" * 72)
    print("#  PRUEBA DE include_tierra=True — NSAC")
    print("#")
    print(f"#  Sitio de partida: {args.sitio} ({sitio['cuerpo']})")
    print(f"#  {sitio['nota']}")
    print("#")
    print("#  A continuación: la MISMA llamada de siempre, pero con")
    print("#  incluir_tierra=True, para que el dict traiga la sección extra")
    print("#  'analogos_tierra' con los datasets terrestres equivalentes.")
    print("#" * 72)

    # ----------------------------------------------------------------------
    # 1) La llamada con el parámetro booleano activado.
    #    usar_gds=False por defecto aquí porque lo que probamos es la parte
    #    terrestre, y los GDS lunares tardan minutos (usa --completo para todo).
    # ----------------------------------------------------------------------
    datos = obtener_datos_sitio(
        cuerpo=sitio["cuerpo"],
        lat=sitio["lat"],
        lon=sitio["lon"],
        radio=sitio["radio"],
        usar_gds=args.completo,
        incluir_tierra=True,          # <-- el parámetro que probamos
    )

    if "analogos_tierra" not in datos:
        print("\nERROR: no vino la sección 'analogos_tierra' (¿parámetro no pasado?)")
        return

    barra(f"LADO TIERRA para comparar con {args.sitio.upper()}")
    mostrar_tierra(datos["analogos_tierra"], sitio["lat"], sitio["lon"])

    # ----------------------------------------------------------------------
    # 2) Segunda demostración: `datos_tierra` se puede llamar SOLO, sin sitio
    #    lunar. Así se construye la tabla de CANDIDATOS terrestres: cada uno
    #    con sus colecciones, y luego se puntúa igual que el sitio lunar.
    # ----------------------------------------------------------------------
    barra("SEGUNDA PRUEBA: datos_tierra() para un candidato terrestre")
    lat_atc, lon_atc = -24.5, -69.25   # desierto de Atacama (Chile)
    print(f"\n  Candidato terrestre: Desierto de Atacama (lat {lat_atc}, lon {lon_atc})")
    print("  Es el análogo clásico de Marte: hiperárido, altura, UV extrema.")
    atacama = datos_tierra(lat_atc, lon_atc, 0.5)
    mostrar_tierra(atacama, lat_atc, lon_atc)

    barra("CÓMO SE USA ESTO PARA FILTRAR ANÁLOGOS")
    print("  1. Del lado lunar/marciano: los valores crudos ya están en el dict")
    print("     (temperatura en K, pendiente en grados, albedo 0-1...).")
    print("  2. Del lado terrestre: estas colecciones CMR dan la MISMA medida")
    print("     (ASTER/SRTM = elevación en m, MODIS LST = temperatura en K,")
    print("     MODIS BRDF = albedo 0-1). Mismas unidades -> comparables 1 a 1.")
    print("  3. La descarga de granules necesita cuenta gratuita de Earthdata:")
    print(f"       earthaccess.login()")
    print(f"       earthaccess.search_data(concept_id='<el de arriba>', bbox=(...))")
    print("  4. Con ambos vectores normalizados, el análogo es el candidato con")
    print("     MENOR distancia al vector del sitio lunar/marciano.")


if __name__ == "__main__":
    main()
