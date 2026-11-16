"""prueba_tierra_glo90.py — COMPARATIVA del método rápido (sub-rama
`tierra-glo90-rapida`): GLO-90 (tiles de ~4-5 MB) vs GLO-30 (30-50 MB).

Pregunta que responde: ¿merece la pena sacrificar resolución (90 m vs 30 m)
a cambio de una descarga ~10x más rápida en la PRIMERA visita de un sitio?
Los números de calidad salen con la MISMA receta (gradiente + celdas de
100 m), así que la diferencia es puramente de resolución del DEM.

Uso (desde la raíz):
    python -m colector_datos.prueba_tierra_glo90
Borra primero data/cache/dtm/*90m* para forzar frío si quieres repetir.
"""

from __future__ import annotations

import time

from . import topografia_tierra

SITIOS = [
    {"nombre": "Atacama", "lat": -24.08, "lon": -69.47, "radio": 0.05},
    {"nombre": "Death Valley", "lat": 36.5, "lon": -117.1, "radio": 0.1},
    {"nombre": "Haughton", "lat": 75.4, "lon": -89.8, "radio": 0.2},
]


def main() -> None:
    print("=== GLO-30 (referencia: tiles ya medidos en tierra-datos-crudos) ===")
    print("  frío descarga 37-42 MB: 43-196 s (varía con la red); tibio 0.07 s")
    print("  Atacama: elev 1563.6 m · pend 4.723° · rug 2.687 m (30 m/px)")
    print("  Death Valley: elev 898.4 m · pend 19.00° · rug 11.23 m")
    print("\n=== GLO-90 medido ahora (mismos sitios) ===")
    for s in SITIOS:
        t0 = time.perf_counter()
        res = topografia_tierra.analizar_sitio(
            s["lat"], s["lon"], s["radio"], aviso=lambda m: print(f"    · {m}"),
            resolucion="90m")
        dt = time.perf_counter() - t0
        if "error" in res:
            print(f"  {s['nombre']}: ERROR {res['error']}")
            continue
        e, p, r = res["elevacion"], res["pendiente"], res["rugosidad"]
        print(f"  {s['nombre']}: {res.get('resolucion_m')} m/px · "
              f"desc={res.get('descarga_s')}s cómputo={res.get('computo_s')}s "
              f"(pared {dt:.1f}s)")
        print(f"    elev media {e['media']} (std {e['desv_estandar']}) · "
              f"pend {p['media']}° · rug {r['media']} m · n={e['n']}")
    print("\n  Leer las métricas contra GLO-30: la pendiente de 90 m 'suaviza'")
    print("  el terreno corto (igual que LOLA vs DTM en la Luna: NOTAS §9.1).")
    print("  Para '¿se puede aterrizar?' el GLO-30 es más fiel; para una")
    print("  criba rápida de MUCHOS sitios en frío, GLO-90 vale el sacrificio.")


if __name__ == "__main__":
    main()
