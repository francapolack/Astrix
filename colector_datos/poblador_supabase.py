"""poblador_supabase.py — POBLADOR de la nube: lleva el catálogo local de
sitios candidatos a la tabla `sitios_candidatos` de Supabase (PostgreSQL),
rama `supabase-candidatos`.

QUÉ LEE (las dos estructuras de datos del proyecto, sin transformar nada
a mano):
  1) `colector_datos/data/registro_sitios.json` — entradas de
     `obtener_datos_sitio()` (clave `cuerpo@lat,lon±radio`); sube el
     `resumen` unificado tal cual (las claves que la fuente no dio van
     NULL: regla de oro del proyecto, nunca se inventan).
  2) `data/db/sitios_marte.db` — via `db_sitios_marte.sitios_disponibles()`:
     los sitios marcianos 'listo' (topografía DTM + ventana THEMIS).

Las dos listas se FUSIONAN por `sitio_id` (si un sitio está en las dos,
el registro aporta el resumen completo y la DB marciana completa los
metadatos nombre/tipo/mediciones). El resultado se sube por LOTES
(upsert, 100 filas por petición) con `on_conflict='sitio_id'`, así la
carga es RESUMIBLE y repetirla actualiza sin duplicar.

EJECUCIÓN EN SEGUNDO PLANO (requisito): `lanzar_en_segundo_plano()` arranca
`poblar()` en un `threading.Thread` daemon y devuelve el hilo, para que
`ejemplo_uso.py` (o cualquier app) lo invoque sin bloquear el hilo
principal mientras suben los lotes. Los errores de red van al log del
hilo y nunca rompen al llamador.

CREDENCIALES (`.env` junto a la raíz del repo):
    SUPABASE_URL=https://<proyecto>.supabase.co
    SUPABASE_KEY=<service_role key (sk_...), solo para el poblador>
  Se cargan con python-dotenv si está instalado (fallback: parseo propio
  del .env). Antes de correr esto, ejecuta `supabase/esquema_rpc.sql` en
  el SQL Editor del panel.

CLI (desde la raíz):
    python -m colector_datos.poblador_supabase simular   # mapping sin red
    python -m colector_datos.poblador_supabase poblar    # upsert real
    python -m colector_datos.poblador_supabase estado    # hilos en vuelo
"""

from __future__ import annotations

import json
import os
import re
import threading
from pathlib import Path
from typing import Any

from . import constantes
from . import db_sitios_luna
from . import db_sitios_marte

RUTA_REGISTRO = constantes.RUTA_REGISTRO
RUTA_ENV = Path(__file__).resolve().parent.parent / ".env"

# Límite de almacenamiento del poblador (plan Free de Supabase: 500 MB por
# proyecto; se trabaja con margen). Sobreescible con NSAC_SUPABASE_LIMITE_MB.
# Antes de CADA lote se consulta `uso_bd()` (RPC de supabase/rpc_v2.sql) y,
# si la tabla está al límite, la subida SE DETIENE (nunca se pisa el plan).
# El orden de subida es por SECTOR DE PRIORIDAD: tierra -> luna -> marte,
# así lo valioso ya está en la nube cuando el guardián corta.
LIMITE_MB_DEFECTO = 450.0
SECTOR_PRIORIDAD = ("tierra", "luna", "marte")

# Columnas de la tabla Supabase que salen del 'resumen' unificado
# (las claves coinciden 1:1: el SQL define la tabla A PARTIR de ellas).
CLAVES_RESUMEN = (
    "elevacion_media_m", "pendiente_media_grados", "rugosidad_media_m",
    "temperatura_media_k", "diferencia_dia_noche_k", "variacion_estacional_k",
    "reflectancia_media", "energia_solar_media_wm2", "fraccion_diurna",
    "n_puntos_lola", "n_observaciones_diviner", "via_topografia")

TAMANO_LOTE = 100   # filas por petición de upsert (rápido sin atascar la API)

# Regex de la clave del registro: cuerpo@lat,lon±radio (± es el carácter
# unicode que usa guardar_en_registro en api.py).
_RE_CLAVE = re.compile(r"^(?P<cuerpo>\w+)@(?P<lat>-?\d+(?:\.\d+)?),"
                       r"(?P<lon>-?\d+(?:\.\d+)?)±(?P<radio>\d+(?:\.\d+)?)$")

# Hilos de población en vuelo (para `estado` y para no duplicar).
_HILOS: list[threading.Thread] = []
_LOCK_HILOS = threading.Lock()

# El registro guarda el cuerpo en su código interno ('earth'/'moon'/'mars',
# lo que produce utilidades.normalizar_cuerpo); la tabla de Supabase y el
# catálogo usan el nombre en español ('tierra'/'luna'/'marte'). Se traduce
# al subir, para que el check del SQL valide.
_CUERPO_ES = {"earth": "tierra", "moon": "luna", "mars": "marte"}


# ---------------------------------------------------------------------------
# 1. Entorno (.env) y cliente
# ---------------------------------------------------------------------------

def _cargar_dotenv() -> None:
    """Carga .env en os.environ (python-dotenv si está; fallback propio).

    NO pisa variables ya definidas (misma pauta que python-dotenv).
    """
    if os.environ.get("SUPABASE_URL") and os.environ.get("SUPABASE_KEY"):
        return  # ya están en el entorno: no hace falta .env
    if (Path(__file__).resolve().parent.parent / ".env").exists():
        try:
            from dotenv import load_dotenv
            load_dotenv()
            return
        except ImportError:
            pass  # sin python-dotenv: parseo propio (abajo)
    ruta = RUTA_ENV
    if ruta.exists():
        for linea in ruta.read_text(encoding="utf-8").splitlines():
            linea = linea.strip()
            if not linea or linea.startswith("#") or "=" not in linea:
                continue
            clave, valor = linea.split("=", 1)
            clave, valor = clave.strip(), valor.strip().strip('"').strip("'")
            if clave and clave not in os.environ:
                os.environ[clave] = valor


def _cliente():
    """Cliente de supabase-py (import protegido con instrucción clara)."""
    _cargar_dotenv()
    url = os.environ.get("SUPABASE_URL")
    clave = (os.environ.get("SUPABASE_KEY")
             or os.environ.get("SUPABASE_SERVICE_KEY"))
    if not url or not clave:
        raise RuntimeError(
            "faltan credenciales: copia .env.example a .env y rellena "
            "SUPABASE_URL (https://<proyecto>.supabase.co) y SUPABASE_KEY "
            "(service_role key del panel: Settings -> API). Antes de "
            "poblar, ejecuta supabase/esquema_rpc.sql en el SQL Editor.")
    try:
        from supabase import create_client
    except ImportError as exc:
        raise RuntimeError(
            f"falta la librería supabase ({exc}): pip install supabase"
        ) from exc
    return create_client(url, clave)


# ---------------------------------------------------------------------------
# 2. Lectura de las estructuras locales
# ---------------------------------------------------------------------------

def _nombre_conocido(cuerpo: str, lat: float, lon: float) -> str | None:
    """Nombre del preset/catalogo que coincida con las coordenadas (redondeo
    a 2 decimales; los sitios del cargador se registraron así).

    `cuerpo` puede venir como código interno ('earth') o en español
    ('tierra'): se normaliza a español para comparar con los catálogos.
    """
    cuerpo_es = _CUERPO_ES.get(cuerpo, cuerpo)
    from .cargador_sitios import lista_sitios
    for s in lista_sitios():
        if (s["cuerpo"] == cuerpo_es
                and abs(s["lat"] - lat) < 0.01
                and abs(s["lon"] - lon) < 0.01):
            return s["nombre"]
    return None


def filas_de_registro() -> list[dict[str, Any]]:
    """Entradas del registro -> filas de `sitios_candidatos`.

    Solo entra el sitio si el resumen tiene AL MENOS UN parámetro
    (una fila todo-NULL nunca devolvería similitud; se salta con nota).
    """
    if not RUTA_REGISTRO.exists():
        return []
    registro = json.loads(RUTA_REGISTRO.read_text(encoding="utf-8"))
    filas: list[dict[str, Any]] = []
    for clave, entrada in registro.items():
        if clave.startswith("_") or "resumen" not in entrada:
            continue
        m = _RE_CLAVE.match(clave)
        if not m:
            continue  # clave no estándar: se ignora (no rompe la carga)
        resumen = entrada.get("resumen") or {}
        if not any(k in CLAVES_RESUMEN and resumen.get(k) is not None
                   for k in CLAVES_RESUMEN):
            continue  # sitio sin ningún dato: no aporta a la similitud
        lat, lon = float(m.group("lat")), float(m.group("lon"))
        cuerpo_interno = m.group("cuerpo")
        fila: dict[str, Any] = {
            "sitio_id": clave,
            "cuerpo": _CUERPO_ES.get(cuerpo_interno, cuerpo_interno),
            "lat": lat, "lon": lon,
            "radio_grados": float(m.group("radio")),
            "nombre": _nombre_conocido(cuerpo_interno, lat, lon),
            "fecha_consulta": entrada.get("fecha_consulta"),
            "extra": {},   # (las 'fuentes' van en datos_completos, no aquí)
        }
        for k in CLAVES_RESUMEN:
            if resumen.get(k) is not None:
                fila[k] = resumen[k]
        filas.append(fila)
    return filas


def filas_de_db_marte() -> list[dict[str, Any]]:
    """Sitios 'listo' de `db_sitios_marte` -> filas (cuerpo='marte').

    Reutiliza `sitios_disponibles(solo_listos=True)`, que ya devuelve el
    resumen con EXACTAMENTE las claves del registro + metadatos de la DB.
    """
    return _filas_de_db_gazetteer(db_sitios_marte, "marte")


def filas_de_db_luna() -> list[dict[str, Any]]:
    """Sitios 'listo' de `db_sitios_luna` -> filas (cuerpo='luna').

    MISMA estructura que la marciana (mismo esquema de DB, mismo formato
    de resumen; `via_topografia='dtm_kaguya'`): la paridad luna/marte
    viene de que las dos DBs de gazetteer son gemelas.
    """
    return _filas_de_db_gazetteer(db_sitios_luna, "luna")


def _filas_de_db_gazetteer(modulo, cuerpo: str) -> list[dict[str, Any]]:
    """Común de las dos DBs de gazetteer (marte/luna): mismas claves."""
    filas: list[dict[str, Any]] = []
    for s in modulo.sitios_disponibles(solo_listos=True):
        resumen = s.get("resumen") or {}
        if not any(resumen.get(k) is not None for k in CLAVES_RESUMEN):
            continue
        fila: dict[str, Any] = {
            "sitio_id": s["sitio_id"],
            "cuerpo": cuerpo,
            "nombre": s.get("nombre"),
            "tipo": s.get("tipo"),
            "lat": s["lat"], "lon": s["lon"],
            "radio_grados": s.get("radio_grados", 0.05),
            "fecha_consulta": s.get("actualizado"),
            "extra": {"topografia_extra": s.get("topografia_extra"),
                      "mediciones": s.get("mediciones"),
                      "diametro_km": s.get("diametro_km")},
        }
        for k in CLAVES_RESUMEN:
            if resumen.get(k) is not None:
                fila[k] = resumen[k]
        filas.append(fila)
    return filas


def filas_unificadas() -> list[dict[str, Any]]:
    """Fusión por sitio_id: registro (resumen completo) + las DOS DBs de
    gazetteer (marte y luna: metadatos/mediciones); la DB completa claves
    que el registro no tenga. La lista sale ORDENADA POR SECTOR DE
    PRIORIDAD (tierra -> luna -> marte): si el guardián de almacenamiento
    corta la subida, lo primero valioso ya está en la nube."""
    fusion: dict[str, dict[str, Any]] = {}
    for f in filas_de_db_marte():
        fusion[f["sitio_id"]] = f
    for f in filas_de_db_luna():
        fusion.setdefault(f["sitio_id"], f)
    for f in filas_de_registro():
        base = fusion.get(f["sitio_id"], {})
        base.update({k: v for k, v in f.items()
                     if v is not None or k not in base})
        fusion[f["sitio_id"]] = base

    prioridad = {c: i for i, c in enumerate(SECTOR_PRIORIDAD)}
    return sorted(fusion.values(),
                  key=lambda f: prioridad.get(f["cuerpo"], 99))


def _limite_bytes() -> float:
    """Límite de trabajo del poblador en bytes (env NSAC_SUPABASE_LIMITE_MB,
    default 450 MB: margen sobre los 500 MB del plan Free)."""
    try:
        return float(os.environ.get("NSAC_SUPABASE_LIMITE_MB",
                                    LIMITE_MB_DEFECTO)) * 1e6
    except ValueError:
        return LIMITE_MB_DEFECTO * 1e6


def uso_nube(cliente=None) -> dict[str, Any]:
    """Consume el RPC `uso_bd()` (supabase/rpc_v2.sql): tamaño de la base,
    de la tabla y nº de filas. Devuelve {'error': ...} si el RPC no existe
    todavía (esquema base sin actualizar): el guardián degrada, no rompe."""
    try:
        cliente = cliente or _cliente()
    except RuntimeError as exc:
        return {"error": str(exc)}
    try:
        r = cliente.rpc("uso_bd", {}).execute()
        d = r.data
        if isinstance(d, list) and d:
            d = d[0]
        return d if isinstance(d, dict) else {"error": "respuesta rara"}
    except Exception as exc:
        return {"error": str(exc)}


# ---------------------------------------------------------------------------
# 3. Población (lotes + hilo en segundo plano)
# ---------------------------------------------------------------------------

def poblar(lote: int = TAMANO_LOTE, simular: bool = False,
           aviso=None) -> dict[str, Any]:
    """Sube el catálogo unificado a Supabase por lotes (upsert resumible).

    `simular=True` no toca la red: imprime el mapping (verificación sin
    credenciales). Devuelve contadores; NUNCA lanza hacia el hilo
    llamador: los fallos van en el dict de salida.
    """
    def _aviso(msg: str) -> None:
        if aviso:
            aviso(msg)

    t0 = __import__("time").perf_counter()
    filas = filas_unificadas()
    _aviso(f"catálogo unificado: {len(filas)} sitios "
           f"(tierra={sum(1 for f in filas if f['cuerpo'] == 'tierra')}, "
           f"luna={sum(1 for f in filas if f['cuerpo'] == 'luna')}, "
           f"marte={sum(1 for f in filas if f['cuerpo'] == 'marte')})")
    if not filas:
        return {"subidos": 0, "nota": "catálogo vacío: corre antes "
                "python -m colector_datos.cargador_sitios"}

    if simular:
        for f in filas[:5]:
            _aviso("  " + json.dumps(f, ensure_ascii=False, default=str))
        return {"subidos": 0, "simulado": True, "filas_mapeadas": len(filas)}

    try:
        cliente = _cliente()
    except RuntimeError as exc:
        return {"subidos": 0, "error": str(exc)}

    # --- guardián de almacenamiento (plan Free: 500 MB) -------------------
    limite_bytes = _limite_bytes()
    uso = uso_nube(cliente)
    if uso:
        if uso.get("error"):
            _aviso(f"[espacio] uso_bd no disponible ({uso['error'][:80]}): "
                   "la subida sigue SIN guardián (ejecuta rpc_v2.sql)")
        else:
            mb = uso["bytes_base_datos"] / 1e6
            _aviso(f"[espacio] base de datos: {mb:.1f} MB "
                   f"(tabla sitios_candidatos: "
                   f"{uso['bytes_tabla'] / 1e6:.2f} MB, "
                   f"{uso['filas']} filas; límite de trabajo "
                   f"{limite_bytes / 1e6:.0f} MB)")
            if uso["bytes_base_datos"] >= limite_bytes:
                return {"subidos": 0, "detenido": "espacio",
                        "detalle": f"la base ocupa {mb:.0f} MB >= límite "
                                   f"{limite_bytes / 1e6:.0f} MB: no se "
                                   "sube nada más (plan Free 500 MB). "
                                   "Prioridad ya aplicada: tierra -> "
                                   "luna -> marte."}

    subidos, errores = 0, []
    for i in range(0, len(filas), lote):
        bloque = filas[i:i + lote]
        if uso and not uso.get("error"):
            # Re-chequeo antes de CADA lote: si la base llega al límite en
            # medio de la carga, se corta limpio (los lotes ya subidos
            # quedan; repetir la llamada continúa).
            uso2 = uso_nube(cliente)
            if uso2 and not uso2.get("error") \
                    and uso2["bytes_base_datos"] >= limite_bytes:
                errores.append(f"lote {i // lote + 1}: DETENIDO por "
                               f"límite de espacio "
                               f"({uso2['bytes_base_datos'] / 1e6:.0f} MB)")
                break
        try:
            cliente.table("sitios_candidatos").upsert(
                bloque, on_conflict="sitio_id").execute()
            subidos += len(bloque)
            _aviso(f"  lote {i // lote + 1}: +{len(bloque)} "
                   f"(total {subidos}/{len(filas)})")
        except Exception as exc:
            texto = str(exc)[:200]
            # Diagnóstico del fallo más común (panel con RLS activada):
            # 42501 = "row-level security policy" -> la key NO salta RLS,
            # es decir, se usó la anon/publishable en vez de la service_role.
            if "42501" in texto or "row-level security" in texto:
                texto += (" | la key no salta RLS: usa la SERVICE_ROLE key "
                          "del panel (Settings -> API, la 'service_role'/"
                          "'secret', NO la anon/publishable) en SUPABASE_KEY")
            errores.append(f"lote {i // lote + 1}: {texto}")
    return {"subidos": subidos, "total": len(filas),
            "errores": errores,
            "segundos": round(__import__("time").perf_counter() - t0, 1)}


def lanzar_en_segundo_plano(aviso=None, lote: int = TAMANO_LOTE,
                            simular: bool = False) -> threading.Thread:
    """Arranca `poblar()` en un hilo daemon y lo devuelve (sin bloquear).

    Para llamarlo desde `ejemplo_uso.py` / apps: el hilo muere solo al
    cerrar el proceso si no terminó, y sus errores van al callback de
    aviso, nunca como excepción al llamador.
    """
    def _trabajo() -> None:
        try:
            res = poblar(lote=lote, simular=simular,
                         aviso=lambda m: _log_hilo(m, aviso))
            _log_hilo(f"poblador terminó: "
                      f"{json.dumps(res, ensure_ascii=False, default=str)}",
                      aviso)
        except Exception as exc:  # red caída, key inválida, lo que sea
            _log_hilo(f"poblador FALLO: {exc}", aviso)
        finally:
            with _LOCK_HILOS:
                if _HILOS and _HILOS[0] is threading.current_thread():
                    _HILOS.pop(0)

    hilo = threading.Thread(target=_trabajo, name="poblador-supabase",
                            daemon=True)
    with _LOCK_HILOS:
        _HILOS.append(hilo)
    hilo.start()
    return hilo


def _log_hilo(msg: str, aviso=None) -> None:
    """Log del hilo: al callback del llamador y, si no hay, a stdout."""
    if aviso:
        try:
            aviso(f"[nube] {msg}")
        except Exception:
            pass
    else:
        print(f"[nube] {msg}", flush=True)


def estado_hilos() -> dict[str, Any]:
    """Hilos de población vivos (para el CLI `estado`)."""
    with _LOCK_HILOS:
        return {"hilos_vivos": [h.name for h in _HILOS if h.is_alive()]}


def main() -> None:
    import argparse

    ap = argparse.ArgumentParser(
        description="Poblador de Supabase (ver docstring).")
    sub = ap.add_subparsers(dest="comando", required=True)
    sub.add_parser("poblar", help="upsert real en sitios_candidatos")
    sub.add_parser("simular", help="muestra el mapping sin tocar la red")
    sub.add_parser("estado", help="hilos de población en vuelo")
    args = ap.parse_args()

    if args.comando == "estado":
        print(json.dumps(estado_hilos(), ensure_ascii=False))
    elif args.comando == "simular":
        print(json.dumps(poblar(simular=True, aviso=lambda m: print(m)),
                         ensure_ascii=False, indent=1, default=str))
    else:
        print(json.dumps(poblar(aviso=lambda m: print(m, flush=True)),
                         ensure_ascii=False, indent=1, default=str))


if __name__ == "__main__":
    main()
