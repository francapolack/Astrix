"""cargador_sitios.py — CARGA MASIVA de sitios candidatos a ±0.05° en el
registro local (`data/registro_sitios.json`), rama `supabase-candidatos`.

PROPÓSITO: alimentar la fase de evaluación (buscador de análogos en la nube,
`poblador_supabase.py` → Supabase). Construye el catálogo de sitios
candidatos — análogos terrestres de `constantes.CATALOGO_ANALOGOS_TIERRA` +
los presets lunares/marcianos de `SITIOS` — y les corre
`obtener_datos_sitio()` con radio 0.05, de modo que cada sitio queda en el
registro con el MISMO `resumen` unificado que el resto del proyecto
(mismas claves, mismas unidades; las fuentes que no dan un dato no aportan
esa clave — nunca se inventa).

OPTIMIZACIÓN DE TIEMPO (el requisito de esta carga: margen mínimo):
  - SALTAR lo ya cargado: si la clave `cuerpo@lat,lon±radio` ya está en el
    registro, no se vuelve a consultar (los datos son históricos); usar
    `--refrescar` para forzar una recarga.
  - PARALELISMO: un pool de 3 hilos (misma cortesía que usa api.py: no
    castigar a los servidores).
  - TIERRA vía GLO-90 por defecto (frío 2-10 s vs 43-196 s de GLO-30): el
    tile de 4-5 MB baja ~10x más rápido; elevación idéntica al 0.1 % y
    `via_topografia='glo90'` deja trazado el sacrificio de resolución
    (NOTAS §20-bis). `--glo30` para la versión de máxima fidelidad.
  - LUNA/MARTE SIN GDS (`usar_gds=False`): topografía por DTM remoto
    (~6-15 s por sitio); el térmico Diviner (minutos) queda para una
    corrida aparte — un sitio sin térmico simplemente no aporta esas
    claves al resumen.
  - NADA se descarga completo: tiles DTM a caché, ventanas S2 a caché
    `.npz`, POWER es 2 peticiones JSON. Corridas siguientes salen del
    disco (tibio ~4-5 s por sitio).
  - POLARES LUNARES: el DTM Kaguya miente en los polos (huecos de
    sombra: Malapert medido = 2 % de píxeles válidos, NOTAS §9), así
    que shackleton/malapert/peary QUEDAN SIN topografía en la vía
    rápida. `--gds` los caracteriza completos (Diviner + LOLA vía GDS,
    VARIOS MINUTOS por sitio); con `--gds` conviene `--hilos 1` (el GDS
    es frágil con muchas consultas concurrentes).

CLI (desde la raíz):
    python -m colector_datos.cargador_sitios               # todo el catálogo
    python -m colector_datos.cargador_sitios --solo tierra  # por cuerpo
    python -m colector_datos.cargador_sitios --max 4        # muestra corta
    python -m colector_datos.cargador_sitios --refrescar --glo30
    python -m colector_datos.cargador_sitios --solo luna --gds --hilos 1
"""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from . import constantes

RADIO_CARGA = 0.05   # la caja de comparación del proyecto (±0.05°)
HILOS = 3            # misma cortesía que api.py con los servidores


def lista_sitios(solo_cuerpo: str | None = None) -> list[dict[str, Any]]:
    """Catálogo de sitios a ±0.05: tierra (análogos) + luna/marte (presets).

    Los presets de `SITIOS` usan radios mayores (0.2-0.5°) para la
    exploración interactiva; para la DB de candidatos se RECORTAN a 0.05:
    es la caja donde las tres vías de topografía son comparables y la que
    el GDS soporta sin minutos de espera.
    """
    sitios: list[dict[str, Any]] = []

    if solo_cuerpo in (None, "tierra"):
        for a in constantes.CATALOGO_ANALOGOS_TIERRA:
            sitios.append({"cuerpo": "tierra", "nombre": a["nombre"],
                           "lat": a["lat"], "lon": a["lon"],
                           "radio": RADIO_CARGA, "nota": a["nota"]})

    if solo_cuerpo in (None, "luna", "marte"):
        for clave, s in constantes.SITIOS.items():
            if solo_cuerpo and s["cuerpo"] != solo_cuerpo:
                continue
            sitios.append({"cuerpo": s["cuerpo"], "nombre": clave,
                           "lat": s["lat"], "lon": s["lon"],
                           "radio": min(s["radio"], RADIO_CARGA),
                           "nota": s["nota"]})
    return sitios


def _clave(cuerpo: str, lat: float, lon: float, radio: float) -> str:
    """Clave EXACTA que usa el registro (`guardar_en_registro` en api.py)."""
    return f"{cuerpo}@{lat},{lon}±{radio}"


def cargar(solo_cuerpo: str | None = None, refrescar: bool = False,
           resolucion_tierra: str = "90m", max_sitios: int | None = None,
           usar_gds: bool = False, hilos: int = HILOS,
           aviso=None) -> dict[str, Any]:
    """Carga los sitios del catálogo en el registro, en paralelo.

    Devuelve contadores + tiempos de la corrida. NUNCA lanza: un sitio que
    falla se anota en 'errores' y la carga sigue (misma pauta que el
    resto del colector: los fallos van en el dict, con nota honesta).
    """
    def _aviso(msg: str) -> None:
        if aviso:
            aviso(msg)

    from .api import obtener_datos_sitio
    import json
    from pathlib import Path

    # --- qué queda por cargar (saltar lo ya en registro) ------------------
    ruta_registro = Path(constantes.RUTA_REGISTRO)
    ya_hay: set[str] = set()
    if ruta_registro.exists():
        try:
            ya_hay = {k for k in json.loads(
                ruta_registro.read_text(encoding="utf-8"))
                if not k.startswith("_")}
        except Exception:
            ya_hay = set()

    pendientes: list[dict[str, Any]] = []
    for s in lista_sitios(solo_cuerpo)[:max_sitios or None]:
        clave = _clave(s["cuerpo"], s["lat"], s["lon"], s["radio"])
        if clave in ya_hay and not refrescar:
            _aviso(f"ya en registro: {s['nombre']} ({clave}) — salto")
            continue
        s["clave"] = clave
        pendientes.append(s)

    if not pendientes:
        _aviso("nada que cargar: el catálogo ya está en el registro "
               "(--refrescar para recargar)")
        return {"cargados": 0}

    # --- paralelo: 3 hilos, mismos resumen y registro que una consulta suelta
    t0 = time.perf_counter()
    resultados: dict[str, float] = {}
    errores: list[str] = []
    indice = {"i": 0}

    def _procesar(s: dict[str, Any]) -> None:
        i = indice["i"] = indice["i"] + 1
        t_site = time.perf_counter()
        _aviso(f"[{i}/{len(pendientes)}] {s['nombre']} "
               f"({s['cuerpo']} {s['lat']}, {s['lon']})...")
        try:
            d = obtener_datos_sitio(
                cuerpo=s["cuerpo"], lat=s["lat"], lon=s["lon"],
                radio=s["radio"],
                usar_gds=usar_gds,   # GDS lunar: minutos; ver --gds
                resolucion_topografia=resolucion_tierra if
                s["cuerpo"] == "tierra" else "30m",  # (no aplica fuera de tierra)
                aviso=lambda m: _aviso(f"    · {m}"))
            resultados[s["clave"]] = time.perf_counter() - t_site
            via = (d.get("topografia", {}) or {}).get("via") or "—"
            e = d.get("termico", {}).get("error")
            if e:
                _aviso(f"    · térmico sin dato: {str(e)[:80]}")
            _aviso(f"    OK {s['nombre']} via={via} en "
                   f"{time.perf_counter() - t_site:.1f}s")
        except Exception as exc:
            errores.append(f"{s['nombre']}: {exc}")
            _aviso(f"    FALLO: {exc}")

    with ThreadPoolExecutor(max_workers=hilos) as pool:
        futuros = [pool.submit(_procesar, s) for s in pendientes]
        for f in as_completed(futuros):
            f.result()

    resumen = {
        "sitios_catalogo": len(lista_sitios(solo_cuerpo)),
        "cargados": len(resultados),
        "errores": errores,
        "segundos": round(time.perf_counter() - t0, 1),
        "s_por_sitio": {k: round(v, 1) for k, v in resultados.items()},
        "resolucion_tierra": resolucion_tierra,
        "registro": str(ruta_registro),
    }
    _aviso("carga: " + json.dumps(
        {**resumen, "s_por_sitio": "…"}, ensure_ascii=False))
    return resumen


def main() -> None:
    import argparse
    import json

    def _aviso(msg: str) -> None:
        print(msg, flush=True)

    ap = argparse.ArgumentParser(
        description="Carga masiva de sitios candidatos a ±0.05° en el "
                    "registro (ver docstring).")
    ap.add_argument("--solo", choices=("tierra", "luna", "marte"),
                    help="cargar solo un cuerpo")
    ap.add_argument("--max", type=int, default=None,
                    help="cuántos sitios del catálogo procesar")
    ap.add_argument("--refrescar", action="store_true",
                    help="recarga aunque la clave ya esté en el registro")
    ap.add_argument("--glo30", action="store_true",
                    help="tierra con GLO-30 (fidelidad) en vez de GLO-90")
    ap.add_argument("--gds", action="store_true",
                    help="usa el GDS de PDS (Diviner + LOLA): caracterización "
                         "COMPLETA lunar/marciana pero VARIOS MINUTOS por "
                         "sitio; ideal para los polos lunares (el DTM Kaguya "
                         "no los cubre)")
    ap.add_argument("--hilos", type=int, default=HILOS,
                    help=f"hilo del pool de consultas (default {HILOS}; "
                         "bajar a 1 con --gds: el GDS es frágil con "
                         "consultas concurrentes)")
    a = ap.parse_args()

    res = cargar(solo_cuerpo=a.solo, refrescar=a.refrescar,
                 resolucion_tierra="30m" if a.glo30 else "90m",
                 max_sitios=a.max, usar_gds=a.gds, hilos=a.hilos,
                 aviso=_aviso)
    print(json.dumps(res, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
