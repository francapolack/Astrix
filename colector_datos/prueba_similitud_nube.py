"""prueba_similitud_nube.py — CLIENTE DE PRUEBA de la búsqueda de análogos
en la nube (rama `supabase-candidatos`).

QUÉ HACE:
  1) Carga `SUPABASE_URL` / `SUPABASE_KEY` del `.env` (python-dotenv, con
     fallback de parseo propio del módulo poblador).
  2) Construye un perfil ideal con PESOS (por defecto 80 % pendiente,
     20 % elevación) — opcionalmente extraído de un sitio REAL del registro
     local con `--perfil-desde 'marte@18.38,77.58±0.15'`.
  3) POR DEFECTO llama al RPC `buscar_analogos_v2` (definido en
     `supabase/rpc_v2.sql`, a ejecutar en el panel DESPUÉS del esquema
     base): Top 1 de LUNA, Top 1 de MARTE (cada cuerpo con su API propia)
     y Top 5 de la TIERRA con similitud INDEPENDIENTE por categoría de
     datos (topografia/termico/superficie/iluminacion) + la global.
     Con `--cuerpo luna|marte|tierra` usa la API del cuerpo solo
     (`buscar_analogo_cuerpo`) con `--topn` resultados.

Uso (desde la raíz):
    python -m colector_datos.prueba_similitud_nube
    python -m colector_datos.prueba_similitud_nube --cuerpo luna --topn 3
    python -m colector_datos.prueba_similitud_nube --perfil-desde \
        "earth@-24.08,-69.47±0.05"
    python -m colector_datos.prueba_similitud_nube --perfil '{"fraccion_diurna": {"valor": 0.9, "peso": 1.0}}'
"""

from __future__ import annotations

import argparse
import json

from .poblador_supabase import _cargar_dotenv, filas_de_registro

# Payload por defecto si no hay --perfil / --perfil-desde:
# perfil ideal "de un sitio marciano": pendiente suave (80 %) con
# elevación de valle (~-1500 m, 20 %). Pesos libres (no suman 1: la
# función renormaliza; aquí suman 1 para que sea fácil de leer).
PERFIL_DEFECTO = {
    "pendiente_media_grados": {"valor": 4.0, "peso": 0.8},
    "elevacion_media_m": {"valor": -1500.0, "peso": 0.2},
}


def _perfil_desde_registro(clave: str) -> dict:
    """Perfil ideal a partir de un sitio real del registro local.

    Toma las claves numéricas del resumen con PESOS REPARTIDOS
    automáticamente (equitativos entre los parámetros presentes), útil
    para preguntar "¿qué lugar es más parecido a ESTE sitio?".
    """
    from .poblador_supabase import RUTA_REGISTRO

    registro = json.loads(RUTA_REGISTRO.read_text(encoding="utf-8"))
    if clave not in registro:
        raise SystemExit(f"la clave '{clave}' no está en el registro; "
                         f"corre antes el cargador o usa --perfil")
    resumen = registro[clave]["resumen"]
    numericos = [k for k in resumen if isinstance(resumen.get(k), (int, float))
                 and k not in ("n_puntos_lola", "n_observaciones_diviner")]
    if not numericos:
        raise SystemExit(f"'{clave}' no tiene parámetros numéricos en el "
                         "resumen (¿carga sin GDS y sin térmico?)")
    peso = round(1.0 / len(numericos), 4)
    perfil = {k: {"valor": float(resumen[k]), "peso": peso}
              for k in numericos}
    print(f"perfil derivado de '{clave}' "
          f"({len(numericos)} parámetros con peso {peso} c/u)")
    return perfil


def main() -> None:
    ap = argparse.ArgumentParser(description="Prueba del RPC de similitud "
                                             "en Supabase (ver docstring).")
    ap.add_argument("--perfil", default=None,
                    help="perfil JSON con pesos (por defecto 80%% pendiente "
                         "/ 20%% elevación)")
    ap.add_argument("--perfil-desde", default=None, metavar="CLAVE",
                    help="deriva el perfil de un sitio real del registro "
                         "(p.ej. 'marte@18.38,77.58±0.15')")
    ap.add_argument("--cuerpo", default=None,
                    choices=("tierra", "luna", "marte"),
                    help="API PROPIA de un cuerpo: Top N SOLO de ese cuerpo "
                         "(RPC buscar_analogo_cuerpo). Sin esta opción se "
                         "usa la búsqueda completa v2: luna_top1 + "
                         "marte_top1 + tierra_top5 con desglose por "
                         "categorías")
    ap.add_argument("--topn", type=int, default=1,
                    help="cuántos resultados por cuerpo (con --cuerpo; "
                         "default 1)")
    args = ap.parse_args()

    if args.perfil_desde:
        perfil = _perfil_desde_registro(args.perfil_desde)
    elif args.perfil:
        perfil = json.loads(args.perfil)
    else:
        perfil = PERFIL_DEFECTO

    _cargar_dotenv()
    try:
        from supabase import create_client
        import os
        url, clave = (os.environ.get("SUPABASE_URL"),
                      os.environ.get("SUPABASE_KEY"))
        if not url or not clave:
            raise RuntimeError("sin SUPABASE_URL/SUPABASE_KEY en .env")
        cliente = create_client(url, clave)
    except (ImportError, RuntimeError) as exc:
        raise SystemExit(f"\nX {exc}\n  → copia .env.example a .env, rellena "
                         "SUPABASE_URL y SUPABASE_KEY (service_role), y "
                         "ejecuta supabase/esquema_rpc.sql en el panel.\n")

    print("perfil: " + json.dumps(perfil, ensure_ascii=False))

    if args.cuerpo:
        # --- API propia de un cuerpo: Top N solo de ese cuerpo ------------
        rpc, params = "buscar_analogo_cuerpo", {
            "parametros": {"perfil": perfil},
            "cuerpo": args.cuerpo, "topn": args.topn,
        }
        titulo = f"Top {args.topn} de {args.cuerpo}"
    else:
        # --- búsqueda completa v2 (luna + marte + tierra en una llamada) --
        rpc, params = "buscar_analogos_v2", {"parametros": {"perfil": perfil}}
        titulo = "Búsqueda completa v2 (luna_top1 + marte_top1 + tierra_top5)"
    print(f"\nRPC {rpc} — {titulo}")

    try:
        r = cliente.rpc(rpc, params).execute()
    except Exception as exc:
        texto = str(exc)
        raise SystemExit(
            f"\nX el RPC falló: {texto[:300]}\n"
            "  → si el error menciona 'schema cache' o PGRST202, recarga la\n"
            "    API (Settings -> API -> Reload) tras ejecutar en el panel\n"
            "    supabase/esquema_rpc.sql Y supabase/rpc_v2.sql, y revisa\n"
            "    que la tabla tenga filas (puebla con:\n"
            "    python -m colector_datos.poblador_supabase poblar)\n")

    d = r.data if isinstance(r.data, dict) else json.loads(r.data or "{}")

    CATEGORIAS = ("global", "topografia", "termico", "superficie",
                  "iluminacion")

    def _fila(f: dict) -> str:
        if not f:
            return "— (sin candidato: ¿tabla poblada? ¿similitud NULL?)"
        base = (f"{f.get('nombre') or f.get('sitio_id')} "
                f"[{f.get('cuerpo')}] ({f.get('lat')}, {f.get('lon')}) "
                f"global={f.get('similitud')}")
        s = f.get("similitudes")
        if isinstance(s, dict):
            partes = [f"{c}={_fmt(s.get(c))}" for c in CATEGORIAS[1:]]
            base += " | " + ", ".join(partes)
        return base

    def _fmt(v):
        return "—" if v is None else (f"{v:.3f}" if isinstance(v, (int, float))
                                      else str(v)[:6])

    if args.cuerpo:
        print(f"\n=== Top {args.topn} de {args.cuerpo} "
              f"(vistos: {d.get('vistos')}) ===")
        for f in d.get("resultados") or []:
            print("  " + _fila(f))
    else:
        print("\n=== Luna: Top 1 ===")
        print("  " + _fila(d.get("luna_top1") or {}))
        print("\n=== Marte: Top 1 ===")
        print("  " + _fila(d.get("marte_top1") or {}))
        print("\n=== Tierra: Top 5 (con similitud por categoría) ===")
        for f in d.get("tierra_top5") or []:
            print("  " + _fila(f))
        print(f"\n(vistos: {json.dumps(d.get('vistos') or {})})")
    print("\n'global' = la similitud con TODOS los pesos del perfil; cada "
          "categoría (topografia/termico/superficie/iluminacion) renormaliza "
          "SUS pesos entre los parámetros que la fila tiene. NULL = la fila "
          "no tiene datos de esa categoría (no se inventan números).")


if __name__ == "__main__":
    main()
