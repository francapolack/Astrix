"""carga_fondo.py — ORQUESTADOR DE CARGA COMPLETA en segundo plano (NSAC,
rama `supabase-candidatos`): deja este script corriendo y va llenando TODO
el catálogo de sitios — tierra y marte — primero en el disco local y luego
en Supabase, sin vigilancia.

QUÉ HACE (por fases, todas reanudables: si lo cortas con Ctrl+C, al
repetirlo continúa exactamente donde quedó):

  FASE 1 · TIERRA    `cargador_sitios.cargar('tierra')` → los análogos de
                     `CATALOGO_ANALOGOS_TIERRA` al registro local a ±0.05°
                     (lo ya cargado se SALTA: segunda corrida = 0 s).
  FASE 2 · GAZETTEER `db_sitios_marte.indexar_gazetteer()` SOLO si la DB
                     local está vacía: baja el Gazetteer IAU/USGS y crea
                     los ~1.133 lugares CON NOMBRE como 'pendiente'.
  FASE 3 · MARTE     bucle de `enriquecer(--lote)` hasta agotar los
                     'pendiente': topografía DTM remota (MRO, /vsicurl,
                     sin descargar tiles) + ventana THEMIS vía ODE, por
                     lotes con `--hilos`. Tras CADA lote, `poblar()` sube
                     a Supabase lo nuevo (upsert, resumible): la nube va
                     creciendo mientras el fondo trabaja.
  FASE 4 · LUNA      lo MISMO que Marte pero con `db_sitios_luna`:
                     Gazetteer lunar (Target=16_Moon, ~9.200 lugares ->
                     ~2.090 útiles tras excluir 'Satellite Feature') y
                     topografía por DTM Kaguya (política de api.py:
                     >=50% píxeles válidos Y >=90% cobertura).
  FASE 5 · REINTENTO  los sitios 'error' (fallos de red) vuelven a
                     'pendiente' y se les da OTRA pasada (marte y luna);
                     los 'sin_dtm' (no hay tile que cubra el sitio) quedan
                     como están: honestos, sin números inventados.
  FASE 6 · CIERRE    `poblar()` final + `estado` de las DBs y del registro.

La subida a la nube es por SECTOR DE PRIORIDAD (tierra -> luna -> marte) y
el guardián de `poblar()` consulta `uso_bd()` antes de cada lote: si la
base se acerca al límite del plan Free (500 MB; guardián a 450 MB,
NSAC_SUPABASE_LIMITE_MB), la subida SE DETIENE limpia y lo ya subido
queda (repetir la llamada continúa).

TIEMPO ORIENTATIVO: tierra tibia (ya cargada) = minutos de nada; gazetteer
= 1-2 min; enriquecimiento ~2.100 sitios a 2-5 s/sitio con 3 hilos
≈ 2-3 horas la primera vez (la red manda). El estimado se recalcula tras
el primer lote y se muestra en cada aviso.

EJECUCIÓN (desde la raíz; dejar en una terminal aparte / pestaña):
    python -m colector_datos.carga_fondo                # todo
    python -m colector_datos.carga_fondo --saltear_tierra
    python -m colector_datos.carga_fondo --hilos 2 --lote 30
Requisito previo (una sola vez): `.env` con SUPABASE_URL/SUPABASE_KEY
(service_role) y `supabase/esquema_rpc.sql` ejecutado en el panel. Si no
hay credenciales, el fondo NO se detiene: llena el disco local igual y
avisa que la subida a la nube quedará para cuando existan.
"""

from __future__ import annotations

import json
import time
from typing import Any

from . import constantes
from . import db_sitios_marte
from . import poblador_supabase

LOTE_ENRIQUECER = 50   # sitios por pasada de enriquecer (y de subida)
HILOS = 3              # cortesía con STAC/ODE (el propio módulo tapa a 3)
ESPERA_ENTRE_LOTES_S = 2.0   # respiro entre lotes para los servidores


def _aviso(msg: str) -> None:
    print(msg, flush=True)


# ---------------------------------------------------------------------------
# Fases
# ---------------------------------------------------------------------------

def fase_tierra(refrescar: bool = False) -> dict[str, Any]:
    """Análogos terrestres al registro local (salta lo ya cargado)."""
    from .cargador_sitios import cargar

    _aviso("\n=== FASE 1 · TIERRA (catálogo de análogos a ±0.05°) ===")
    return cargar(solo_cuerpo="tierra", refrescar=refrescar,
                  resolucion_tierra="90m", aviso=_aviso)


def fase_gazetteer() -> dict[str, Any]:
    """Indexa el Gazetteer marciano SOLO si la DB local está vacía."""
    _aviso("\n=== FASE 2 · GAZETTEER MARCIANO (lugares con nombre) ===")
    estado = db_sitios_marte.estado_db()
    if estado["total"] > 0:
        _aviso(f"DB ya indexada: {estado['total']} sitios "
               f"({estado['por_estado']}) — no se re-indexa")
        return {"indexados": 0, "ya_estaba": True}
    return db_sitios_marte.indexar_gazetteer(aviso=_aviso)


def fase_marte(hilos: int = HILOS, lote: int = LOTE_ENRIQUECER,
               sube_a_nube: bool = True,
               muestra: int | None = None) -> dict[str, Any]:
    """Enriquece los 'pendiente' por lotes y sube cada lote a la nube.

    `muestra` acota el total a procesar en ESTA corrida (pequeñas muestras
    para avanzar mientras el fondo completo va por su cuenta); None = todo.
    Devuelve el resumen de la fase. El bucle termina cuando no quedan
    'pendiente' (queda 'sin_dtm'/'listo'); se corta con Ctrl+C sin perder
    nada (cada sitio ya procesado está guardado en la DB).
    """
    _aviso("\n=== FASE 3 · ENRIQUECIMIENTO MARTE (DTM remoto + THEMIS) ===")
    resumen_fase: dict[str, Any] = {"lotes": [], "subidos_nube": 0,
                                    "procesados_corrida": 0}
    pasada = 0

    while True:
        estado = db_sitios_marte.estado_db()
        pendientes = estado["por_estado"].get("pendiente", 0)
        if pendientes == 0:
            break
        if muestra and resumen_fase["procesados_corrida"] >= muestra:
            _aviso(f"-- muestra agotada ({muestra} sitios en esta corrida): "
                   f"quedan {pendientes} para el fondo completo --")
            break
        pasada += 1
        _aviso(f"-- pasada {pasada}: {pendientes} sitios pendientes --")

        objetivo_lote = lote
        if muestra:  # no pasar del tope de la muestra en el último lote
            objetivo_lote = min(lote, muestra
                                - resumen_fase["procesados_corrida"])
        cont = db_sitios_marte.enriquecer(max_sitios=objetivo_lote,
                                          hilos=hilos, aviso=_aviso)
        procesados_lote = (cont.get("listo", 0) + cont.get("sin_dtm", 0)
                           + cont.get("error", 0))
        resumen_fase["procesados_corrida"] += procesados_lote
        resumen_fase["lotes"].append(cont)

        # Subida incremental a la nube (upsert resumible): lo 'listo' del
        # lote ya está en la DB local, poblar() lo fusiona con el registro.
        if sube_a_nube and cont.get("listo", 0) > 0:
            subida = poblador_supabase.poblar(aviso=_aviso)
            resumen_fase["subidos_nube"] += subida.get("subidos", 0)
            if subida.get("error"):
                _aviso(f"[nube] subida diferida: {subida['error'][:120]}")

        # Estimación: la red manda; el primer lote calibra el resto.
        if cont.get("listo", 0) or cont.get("sin_dtm", 0):
            procesados = cont.get("listo", 0) + cont.get("sin_dtm", 0) \
                + cont.get("error", 0)
            if procesados and cont.get("segundos"):
                s_por_sitio = cont["segundos"] / procesados
                resto = db_sitios_marte.estado_db()["por_estado"].get(
                    "pendiente", 0)
                _aviso(f"   ritmo: {s_por_sitio:.1f} s/sitio con {hilos} "
                       f"hilo(s); quedan {resto} -> ~"
                       f"{resto * s_por_sitio / hilos / 60:.0f} min")
        time.sleep(ESPERA_ENTRE_LOTES_S)
    return resumen_fase


def fase_reintento(hilos: int = HILOS, lote: int = LOTE_ENRIQUECER,
                   sube_a_nube: bool = True,
                   muestra: int | None = None) -> dict[str, Any]:
    """Los 'error' (fallos de red puntuales) de MARTE vuelven a 'pendiente'
    y otra pasada. Los 'sin_dtm' NO se reintentan: no hay tile que cubra."""
    con = db_sitios_marte._conectar()
    cur = con.execute(
        "UPDATE sitios SET estado='pendiente', error=NULL "
        "WHERE estado='error'")
    con.commit()
    con.close()
    if cur.rowcount:
        _aviso(f"\n=== FASE 5 · REINTENTO (marte): {cur.rowcount} 'error' "
               "-> 'pendiente' ===")
        return fase_marte(hilos=hilos, lote=lote, sube_a_nube=sube_a_nube,
                          muestra=muestra)
    _aviso("\n=== FASE 5 · REINTENTO (marte): sin sitios 'error' ===")
    return {"reintentados": 0}


# ---------------------------------------------------------------------------
# Fases de LUNA (paridad con Marte: mismo orquestador, otra fuente)
# ---------------------------------------------------------------------------

def fase_gazetteer_luna() -> dict[str, Any]:
    """Indexa el Gazetteer LUNAR SOLO si la DB local está vacía."""
    from . import db_sitios_luna

    _aviso("\n=== FASE 4a · GAZETTEER LUNAR (lugares con nombre) ===")
    estado = db_sitios_luna.estado_db()
    if estado["total"] > 0:
        _aviso(f"DB lunar ya indexada: {estado['total']} sitios "
               f"({estado['por_estado']}) — no se re-indexa")
        return {"indexados": 0, "ya_estaba": True}
    return db_sitios_luna.indexar_gazetteer(aviso=_aviso)


def fase_luna(hilos: int = HILOS, lote: int = LOTE_ENRIQUECER,
              sube_a_nube: bool = True,
              muestra: int | None = None) -> dict[str, Any]:
    """Enriquece los 'pendiente' LUNARES por lotes (DTM Kaguya) y sube
    cada lote a la nube. MISMO bucle que la fase marte, otra DB;
    `muestra` acota el total de esta corrida (ver fase_marte)."""
    from . import db_sitios_luna

    _aviso("\n=== FASE 4b · ENRIQUECIMIENTO LUNA (DTM Kaguya) ===")
    resumen_fase: dict[str, Any] = {"lotes": [], "subidos_nube": 0,
                                    "procesados_corrida": 0}
    while True:
        estado = db_sitios_luna.estado_db()
        pendientes = estado["por_estado"].get("pendiente", 0)
        if pendientes == 0:
            break
        if muestra and resumen_fase["procesados_corrida"] >= muestra:
            _aviso(f"-- muestra agotada ({muestra} sitios en esta corrida): "
                   f"quedan {pendientes} para el fondo completo --")
            break
        _aviso(f"-- {pendientes} sitios lunares pendientes --")
        objetivo_lote = lote
        if muestra:  # no pasar del tope de la muestra en el último lote
            objetivo_lote = min(lote, muestra
                                - resumen_fase["procesados_corrida"])
        cont = db_sitios_luna.enriquecer(max_sitios=objetivo_lote,
                                         hilos=hilos, aviso=_aviso)
        procesados_lote = (cont.get("listo", 0) + cont.get("sin_dtm", 0)
                           + cont.get("error", 0))
        resumen_fase["procesados_corrida"] += procesados_lote
        resumen_fase["lotes"].append(cont)
        if sube_a_nube and cont.get("listo", 0) > 0:
            subida = poblador_supabase.poblar(aviso=_aviso)
            resumen_fase["subidos_nube"] += subida.get("subidos", 0)
            if subida.get("detenido"):
                _aviso(f"[nube] guardián: {subida['detalle'][:140]}")
        if cont.get("segundos") and (cont.get("listo", 0)
                                     or cont.get("sin_dtm", 0)):
            proc = (cont.get("listo", 0) + cont.get("sin_dtm", 0)
                    + cont.get("error", 0))
            s_por = cont["segundos"] / max(1, proc)
            resto = db_sitios_luna.estado_db()["por_estado"].get(
                "pendiente", 0)
            _aviso(f"   ritmo: {s_por:.1f} s/sitio; quedan {resto} -> ~"
                   f"{resto * s_por / hilos / 60:.0f} min")
        time.sleep(ESPERA_ENTRE_LOTES_S)
    return resumen_fase


def fase_reintento_luna(hilos: int = HILOS, lote: int = LOTE_ENRIQUECER,
                        sube_a_nube: bool = True,
                        muestra: int | None = None) -> dict[str, Any]:
    """Los 'error' LUNARES vuelven a 'pendiente' y otra pasada."""
    from . import db_sitios_luna

    con = db_sitios_luna._conectar()
    cur = con.execute(
        "UPDATE sitios SET estado='pendiente', error=NULL "
        "WHERE estado='error'")
    con.commit()
    con.close()
    if cur.rowcount:
        _aviso(f"\n=== FASE 5 · REINTENTO (luna): {cur.rowcount} 'error' "
               "-> 'pendiente' ===")
        return fase_luna(hilos=hilos, lote=lote, sube_a_nube=sube_a_nube,
                         muestra=muestra)
    _aviso("\n=== FASE 5 · REINTENTO (luna): sin sitios 'error' ===")
    return {"reintentados": 0}


def main() -> None:
    import argparse
    import sys

    # Consola Windows: los nombres del Gazetteer llevan diacríticos
    # (p.ej. 'Běla'); sin esto, cp1252 rompe el print. (Equivalente a
    # PYTHONIOENCODING=utf-8 pero sin depender del entorno.)
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    def _aviso(msg: str) -> None:
        print(msg, flush=True)

    ap = argparse.ArgumentParser(
        description="Carga COMPLETA de sitios (tierra+luna+marte) en "
                    "segundo plano, con subida incremental a Supabase (ver "
                    "docstring). Reanudable: cortarlo no pierde nada.")
    ap.add_argument("--hilos", type=int, default=HILOS,
                    help=f"hilo del pool (default {HILOS}; 2-3 máximo: "
                         "cortesía con STAC/ODE)")
    ap.add_argument("--lote", type=int, default=LOTE_ENRIQUECER,
                    help=f"sitios por pasada de enriquecimiento "
                         f"(default {LOTE_ENRIQUECER})")
    ap.add_argument("--muestra", type=int, default=None,
                    help="TOPE de sitios por cuerpo en esta corrida "
                         "(muestras pequeñas para avanzar; sin ella "
                         "procesa TODO lo pendiente)")
    ap.add_argument("--refrescar_tierra", action="store_true",
                    help="recarga los análogos de tierra aunque ya estén")
    ap.add_argument("--saltear_tierra", action="store_true",
                    help="no toca la fase tierra")
    ap.add_argument("--saltear_marte", action="store_true",
                    help="no toca gazetteer/enriquecimiento de marte")
    ap.add_argument("--saltear_luna", action="store_true",
                    help="no toca gazetteer/enriquecimiento de luna")
    ap.add_argument("--sin_nube", action="store_true",
                    help="no sube nada a Supabase (solo disco local)")
    a = ap.parse_args()

    t0 = time.perf_counter()
    sube = not a.sin_nube
    if not sube:
        _aviso("modo --sin_nube: nada se enviará a Supabase")
    elif not (poblador_supabase.RUTA_ENV.exists()):
        _aviso("[nube] sin .env: la subida quedará para cuando existan "
               "credenciales (el fondo sigue con el disco local)")

    try:
        if not a.saltear_tierra:
            fase_tierra(refrescar=a.refrescar_tierra)
        if not a.saltear_marte:
            fase_gazetteer()
            fase_marte(hilos=a.hilos, lote=a.lote, sube_a_nube=sube,
                       muestra=a.muestra)
            fase_reintento(hilos=a.hilos, lote=a.lote, sube_a_nube=sube,
                           muestra=a.muestra)
        if not a.saltear_luna:
            fase_gazetteer_luna()
            fase_luna(hilos=a.hilos, lote=a.lote, sube_a_nube=sube,
                      muestra=a.muestra)
            fase_reintento_luna(hilos=a.hilos, lote=a.lote,
                                sube_a_nube=sube, muestra=a.muestra)
    except KeyboardInterrupt:
        _aviso("\nINTERRUMPIDO por el usuario — todo lo procesado ya está "
               "guardado (DB local resumible + upsert en la nube). "
               "Repite el comando para continuar donde quedó.")
        return

    # --- cierre: última subida (por si el reintento añadió) + estado ------
    if sube:
        _aviso("\n=== FASE 5 · CIERRE: subida final ===")
        poblador_supabase.poblar(aviso=_aviso)
    estado = db_sitios_marte.estado_db()
    _aviso("\n=== ESTADO FINAL ===")
    _aviso(f"DB marciana: {estado['total']} sitios {estado['por_estado']}")
    try:
        import pathlib
        registro = json.loads(
            pathlib.Path(constantes.RUTA_REGISTRO).read_text(
                encoding="utf-8"))
        n_reg = len([k for k in registro if not k.startswith("_")])
        _aviso(f"Registro local: {n_reg} sitios")
    except Exception:
        pass
    _aviso(f"Tiempo total: {(time.perf_counter() - t0) / 60:.1f} min")


if __name__ == "__main__":
    main()
