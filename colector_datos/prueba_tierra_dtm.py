"""prueba_tierra_dtm.py — piloto del paso 1 (rama `tierra-datos-crudos`).

Corre `topografia_tierra.analizar_sitio` en sitios de prueba reales y
compara frío/tibio y modo descargar/remoto, como `prueba_dtm.py` hizo con
Kaguya/LOLA. Los resultados van a NOTAS_NOCTURNAS.md como registro.

Uso (desde la raíz):
    python -m colector_datos.prueba_tierra_dtm                # sitios fijos
    python -m colector_datos.prueba_tierra_dtm --lat -23.4 --lon 157.8 --radio 0.05
    python -m colector_datos.prueba_tierra_dtm --remoto       # fuerza modo remoto
"""

from __future__ import annotations

import argparse
import json
import time

from . import topografia_tierra

# Sitios de prueba: dos análogos clásicos del reto + un tile marino para
# probar la detección de océano + un sitio de la DB marciana para comparar
# la escala de las métricas con la Luna/Marte.
SITIOS = [
    {"nombre": "Atacama (análogo marciano)", "lat": -24.08, "lon": -69.47,
     "radio": 0.05},
    {"nombre": "Death Valley (análogo marciano)", "lat": 36.5, "lon": -117.1,
     "radio": 0.1},
    {"nombre": "Haughton (análogo polar ártico)", "lat": 75.4, "lon": -89.8,
     "radio": 0.2},
    {"nombre": "tile marino (Atlantic)", "lat": 35.0, "lon": -35.0,
     "radio": 0.05},
]


def _resumen(nombres: str, res: dict) -> str:
    if "error" in res:
        return f"{nombres}: ERROR {res['error']}"
    e, p, r = res.get("elevacion", {}), res.get("pendiente", {}), res.get("rugosidad", {})
    extra = ""
    if res.get("nota_oceano"):
        extra = " [OCÉANO]"
    return (f"{nombres}: via={res.get('tile')} res={res.get('resolucion_m')} m/px "
            f"cob={res.get('cobertura_fraccion')} confiable={res.get('confiable')}{extra} "
            f"t={res.get('total_s')}s (desc={res.get('descarga_s')} cómputo={res.get('computo_s')}) "
            f"elev_med={e.get('media')} pend_med={p.get('media')}° "
            f"rug_med={r.get('media')}m n={e.get('n')}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--lat", type=float)
    ap.add_argument("--lon", type=float)
    ap.add_argument("--radio", type=float, default=0.05)
    ap.add_argument("--remoto", action="store_true",
                    help="fuerza modo_tile='remoto' (/vsicurl, sin caché)")
    args = ap.parse_args()

    modo = "remoto" if args.remoto else "descargar"
    sitios = SITIOS
    if args.lat is not None:
        sitios = [{"nombre": "sitio dado", "lat": args.lat, "lon": args.lon,
                   "radio": args.radio}]

    for s in sitios:
        t0 = time.perf_counter()
        res = topografia_tierra.analizar_sitio(
            s["lat"], s["lon"], s["radio"], modo_tile=modo,
            aviso=lambda m: print(f"    · {m}"))
        print(_resumen(f"{s['nombre']} [{modo}]", res))
        if "error" not in res:
            print(f"    total de pared: {time.perf_counter() - t0:.1f}s")
            print(f"    elev: {json.dumps(res['elevacion'], ensure_ascii=False)}")
            print(f"    pend: {json.dumps(res['pendiente'], ensure_ascii=False)}")
            print(f"    rug:  {json.dumps(res['rugosidad'], ensure_ascii=False)}")
            c = res.get("crateres", {})
            print(f"    crateres: n={c.get('n_candidatos')} "
                  f"{json.dumps(c.get('candidatos', [])[:3], ensure_ascii=False)}")


if __name__ == "__main__":
    main()
