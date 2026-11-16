"""prueba_tierra_comparacion.py — verificación del PASO 6 (rama
`tierra-datos-crudos`): la Tierra ya devuelve datos crudos en el MISMO
formato que la Luna y Marte. Este script corre los tres cuerpos y saca
lado a lado las claves del `resumen` del registro (la plantilla de
NOTAS_NOCTURNAS.md §2.3, ahora entre cuerpos).

Uso (desde la raíz):
    python -m colector_datos.prueba_tierra_comparacion            # rápido
    python -m colector_datos.prueba_tierra_comparacion --luna_completa
        # (--luna_completa lanza el GDS lunar de Diviner/LOLA: MINUTOS)

Sitios: Atacama (tierra), Mare Smythii (luna, vía DTM) y Jezero (marte).
Los tres son ejemplos ya usados en las notas; las cachés aceleran las
segundas corridas.
"""

from __future__ import annotations

import time

from .api import obtener_datos_sitio

CLAVES_RESUMEN = (
    "elevacion_media_m", "pendiente_media_grados", "rugosidad_media_m",
    "temperatura_media_k", "diferencia_dia_noche_k", "variacion_estacional_k",
    "reflectancia_media", "energia_solar_media_wm2", "fraccion_diurna",
    "n_puntos_lola", "n_observaciones_diviner", "via_topografia")


def main(luna_completa: bool = False) -> None:
    sitios = [
        {"nombre": "TIERRA — Atacama", "cuerpo": "tierra",
         "lat": -24.08, "lon": -69.47, "radio": 0.05},
        {"nombre": "LUNA — Mare Smythii", "cuerpo": "luna",
         "lat": -23.4, "lon": 157.8, "radio": 0.05},
        {"nombre": "MARTE — Jezero", "cuerpo": "marte",
         "lat": 18.38, "lon": 77.58, "radio": 0.15},
    ]
    resumenes: dict[str, dict] = {}
    for s in sitios:
        print(f"\n=== {s['nombre']} ===")
        t0 = time.perf_counter()
        d = obtener_datos_sitio(
            cuerpo=s["cuerpo"], lat=s["lat"], lon=s["lon"], radio=s["radio"],
            usar_gds=luna_completa,
            aviso=lambda m: print(f"    · {m}"))
        dt = time.perf_counter() - t0
        clave = f"{d['metadatos']['cuerpo']}@{s['lat']},{s['lon']}"
        from .api import _resumen_para_registro
        resumenes[clave] = _resumen_para_registro(d)
        print(f"    total de pared: {dt:.1f}s "
              f"(via={d['topografia'].get('via', '—')})")

    print("\n" + "=" * 78)
    print("  RESUMEN COMPARADO (las claves del registro, lado a lado)")
    print("=" * 78)
    claves = list(resumenes)
    print(f"  {'clave':30} " + " | ".join(f"{c[:20]:20}" for c in claves))
    for k in CLAVES_RESUMEN:
        fila = []
        for c in claves:
            v = resumenes[c].get(k)
            fila.append("—" if v is None else
                        f"{v:.3g}" if isinstance(v, float) else str(v))
        print(f"  {k:30} " + " | ".join(f"{x:20}" for x in fila))
    print("\n  Lectura: mismas claves en los tres cuerpos = comparación 1:1.")
    print("  n_puntos_lola = píxeles del DTM (GLO-30/Kaguya/CTX) o puntos LOLA;")
    print("  en la Tierra el térmico es reanálisis POWER (no Diviner) y")
    print("  n_observaciones_diviner solo existe en la Luna.")


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--luna_completa", action="store_true",
                    help="lanza también el GDS lunar (Diviner/LOLA): minutos")
    a = ap.parse_args()
    main(a.luna_completa)
