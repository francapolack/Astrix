"""Ejemplo de uso del colector de datos NSAC.

Forma de ejecutar (desde la raíz del proyecto):

    python -m colector_datos.ejemplo_uso            # Luna, Shackleton, con GDS
    python -m colector_datos.ejemplo_uso --rapido   # sin GDS (solo catálogos)
    python -m colector_datos.ejemplo_uso --marte    # Marte, Jezero
    python -m colector_datos.ejemplo_uso --tierra   # análogo terrestre

--rapido existe porque las consultas GDS de PDS tardan MINUTOS (el GDS
genera y empaqueta los CSV a mano alzada); para probar que todo responde
basta con los catálogos.
"""

from __future__ import annotations

import argparse
import json

from . import constantes
from .api import obtener_datos_sitio


def main() -> None:
    parser = argparse.ArgumentParser(description="Colector de datos NSAC")
    parser.add_argument("--rapido", action="store_true",
                        help="salta las consultas GDS (tardan minutos)")
    parser.add_argument("--marte", action="store_true",
                        help="caracteriza Jezero (Marte) en vez de Shackleton")
    parser.add_argument("--tierra", action="store_true",
                        help="análogo terrestre (Atacama) en vez de la Luna")
    parser.add_argument("--sitio", default=None,
                        help="clave de constantes.SITIOS (shackleton, malapert, peary, jezero)")
    parser.add_argument("--poblar_nube", action="store_true",
                        help="tras el informe, lanza en SEGUNDO PLANO la "
                             "subida del catalogo local a Supabase "
                             "(poblador_supabase) sin bloquear esta consola")
    args = parser.parse_args()

    # Sitio elegido: el que pase --sitio, o el del modo, o el por defecto.
    clave = args.sitio or ("jezero" if args.marte else "shackleton")
    sitio = constantes.SITIOS[clave]
    print(f"Sitio: {clave} -> {sitio['nota']}")

    if args.tierra:
        from .analogos_tierra import datos_tierra
        datos = datos_tierra(-24.5, -69.25, 0.5)  # desierto de Atacama
    else:
        datos = obtener_datos_sitio(
            cuerpo=sitio["cuerpo"],
            lat=sitio["lat"],
            lon=sitio["lon"],
            radio=sitio["radio"],
            usar_gds=not args.rapido,
        )

    # `default=str` evita que un valor raro rompa el volcado a JSON.
    print(json.dumps(datos, indent=2, ensure_ascii=False, default=str))

    # Gancho opcional de la nube: en un hilo daemon (no bloquea la consola
    # ni depende del resultado de la consulta de arriba). El import va
    # AQUÍ para que la ausencia de la librería supabase no rompa el
    # ejemplo: el propio poblador avisa y sigue.
    if args.poblar_nube:
        import os
        import time as _time
        from .poblador_supabase import _cargar_dotenv, lanzar_en_segundo_plano
        _cargar_dotenv()
        if not (os.environ.get("SUPABASE_URL")
                and os.environ.get("SUPABASE_KEY")):
            print("\n[nube] sin credenciales (SUPABASE_URL/SUPABASE_KEY en "
                  ".env): no se lanza la subida. Copia .env.example a .env, "
                  "rellénalas y ejecuta antes supabase/esquema_rpc.sql en "
                  "el panel.")
        else:
            hilo = lanzar_en_segundo_plano()
            print(f"\n[nube] población de Supabase lanzada en segundo plano "
                  f"(hilo {hilo.name}); la consola sigue libre.")
            # Espera CORTA solo para que los mensajes del primer lote se vean
            # antes de que el intérprete cierre los hilos daemon: si la subida
            # tardara más, el fin del script la corta (para corridas largas
            # usar el CLI: python -m colector_datos.poblador_supabase poblar).
            hilo.join(timeout=15)


if __name__ == "__main__":
    main()
