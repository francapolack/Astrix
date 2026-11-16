"""db_sitios_luna.py — DB LOCAL de sitios LUNARES con nombre (NSAC),
rama `supabase-candidatos`.

PARIDAD CON MARTE: misma estructura que `db_sitios_marte.py` (una fila por
lugar con nombre del Gazetteer IAU/USGS, topografía en el MISMO formato de
comparación del proyecto, estados resumibles pendiente/listo/sin_dtm/error,
INSERT OR IGNORE idempotente) pero adaptada a la Luna:

  - Gazetteer: UNA página con TODOS los lugares con nombre de la Luna
    (planetarynames.wr.usgs.gov/SearchResults?Target=16_Moon&PageSize=500,
    ~24 MB, 9.202 filas verificadas). El código de target NO es el que
    sugiere la intuición: es 16_Moon, no 10_Moon (sondeado 15-nov-2026).
  - Filtro: 'Satellite Feature' FUERA (7.114 de las 9.202 filas son
    epónimos de cráteres satélite tipo "Walther A": denso y poco útil
    para elegir emplazamientos); el resto entra, incluidos TODOS los
    cráteres con nombre (1.666) — en la Luna no hay filtro de diámetro
    como en Marte (allí 40 km dejaba los estructuralmente interesantes;
    aquí el DTM Kaguya de ~10 m/px resuelve cráteres pequeños y el total
    queda ~2.090 sitios, comparable a los 1.133 de Marte).
  - Topografía: DTM Kaguya (SLNTC TC/MI) vía STAC de USGS + lectura remota
    del trozo (/vsicurl), MISMA política RELAJADA que la DB marciana:
    >=50% de píxeles válidos ('confiable') Y >=50% de cobertura de la caja.
    (La política ESTRICTA de api.py — >=90% cobertura — es para cajas de
    ±0.05°; aquí las cajas del gazetteer son 0.05-0.5° y los tiles Kaguya
    a veces no las cubren enteras: con la nota de cobertura el dato sigue
    siendo honesto. Verificado: Lansberg 67% cobertura / 94% píxeles —
    datos reales de un tile que solo cubre 2/3 de la caja.)
    Si falla, el sitio queda 'sin_dtm' (los polos mentirán por los huecos
    de sombra: NOTAS §9). `via_topografia='dtm_kaguya'` (identico a
    obtener_datos_sitio).
  - SIN térmico: el Diviner equivalente (GDS) tarda MINUTOS por sitio y
    esta DB es de criba masiva; el térmico lunar con valores sigue siendo
    cosa de `obtener_datos_sitio(usar_gds=True)` / `--gds`.

Esquema: SOLO la tabla `sitios` (no hay mediciones: THEMIS es de Marte).
La DB es RESUMIBLE: indexar puede repetirse y enriquecer solo procesa
'pendiente'; Ctrl+C no pierde nada.

CLI (desde la raíz):
  python -m colector_datos.db_sitios_luna indexar
  python -m colector_datos.db_sitios_luna enriquecer --max 120 --hilos 3
  python -m colector_datos.db_sitios_luna listar --n 15
  python -m colector_datos.db_sitios_luna reintentar
  python -m colector_datos.db_sitios_luna estado
"""

from __future__ import annotations

import json
import sqlite3
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import Any

from . import constantes, topografia, topografia_dtm, utilidades
from .db_sitios_marte import (  # helpers genéricos del parser, compartidos
    _filas_gazetteer,
    _numero,
)

RUTA_DB = Path(constantes.RUTA_REGISTRO).parent / "db" / "sitios_luna.db"

URL_GAZETTEER = ("https://planetarynames.wr.usgs.gov/SearchResults"
                 "?Target=16_Moon&PageSize=500")

# Política de filtros LUNAR (diferente de la marciana, razonada arriba):
TIPOS_EXCLUIDOS = {"Satellite Feature"}
DIAMETRO_CRATER_MIN_KM_LUNA = 0.0   # TODOS los cráteres con nombre entran

# Lock propio: misma pauta que la DB marciana (SQLite + hilos en Windows).
_LOCK_SQLITE = threading.Lock()

# Política DTM RELAJADA de la criba (la MISMA que la DB marciana): las
# cajas del gazetteer (0.05-0.5°) a veces no caben enteras en los tiles
# Kaguya; la nota de cobertura lo deja trazado. (La política ESTRICTA de
# api.py, >=90% cobertura, es para cajas de ±0.05°.)
COBERTURA_MINIMA = 0.5     # >=50% de la caja dentro del/los tile(s)
PIXELES_VALIDOS_MIN = 0.5  # >=50% de píxeles válidos ('confiable')


# ---------------------------------------------------------------------------
# 1. Conexión y esquema
# ---------------------------------------------------------------------------

def _conectar() -> sqlite3.Connection:
    """Abre la DB lunar (creando carpeta y tabla si falta).

    Mismas columnas que la marciana SALVO las themis_* (aquí no hay
    THEMIS) y sin tabla `mediciones` (no hay ventana que guardar).
    """
    RUTA_DB.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(RUTA_DB, timeout=60)
    con.row_factory = sqlite3.Row
    con.execute("""
        CREATE TABLE IF NOT EXISTS sitios (
            sitio_id     TEXT PRIMARY KEY,   -- 'moon@lat,lon±radio'
            nombre       TEXT NOT NULL,
            tipo         TEXT,
            diametro_km  REAL,
            lat          REAL NOT NULL,
            lon          REAL NOT NULL,
            radio        REAL NOT NULL,
            estado       TEXT DEFAULT 'pendiente',  -- pendiente|listo|sin_dtm|error
            error        TEXT,
            -- topografía (formato de comparación del proyecto)
            elevacion_min_m    REAL,
            elevacion_media_m  REAL,
            elevacion_max_m    REAL,
            elevacion_mediana_m REAL,
            pendiente_media_grados REAL,
            rugosidad_media_m  REAL,
            n_pixeles          INTEGER,
            cobertura          REAL,
            resolucion_m       REAL,
            n_crateres         INTEGER,
            nota               TEXT,
            -- trazabilidad del tile DTM usado
            tile_id      TEXT,
            tile_url     TEXT,
            fuente_dtm   TEXT,
            actualizado  TEXT
        )
    """)
    con.commit()
    return con


# ---------------------------------------------------------------------------
# 2. Indexación del Gazetteer
# ---------------------------------------------------------------------------

def indexar_gazetteer(aviso=None) -> dict[str, Any]:
    """Descarga la página del Gazetteer lunar y llena 'pendiente'.

    Idéntico al marciano salvo: target 16_Moon, filtro de tipos lunar
    (Satellite Feature fuera; TODOS los cráteres entran) y sitio_id
    'moon@...' con radio .3f (cráteres pequeños redondean a 0.05).
    """
    def _aviso(msg: str) -> None:
        if aviso:
            aviso(msg)

    from nsac.http import get
    from .db_sitios_marte import _radio_de

    _aviso(f"descargando Gazetteer ({URL_GAZETTEER}) — son ~24 MB, "
           "paciencia...")
    t0 = time.perf_counter()
    r = get(URL_GAZETTEER, timeout=600)
    filas = _filas_gazetteer(r.text)
    _aviso(f"{len(filas)} lugares parseados en "
           f"{round(time.perf_counter() - t0, 1)} s")

    con = _conectar()
    insertados, excluidos = 0, 0
    with _LOCK_SQLITE:
        for f in filas:
            if len(f) <= 14:
                continue  # fila recortada: fuera
            tipo = f[14]
            if tipo in TIPOS_EXCLUIDOS:
                excluidos += 1
                continue
            nombre = f[1]
            diam = _numero(f[4])
            lat = _numero(f[5])
            lon360 = _numero(f[6])
            if lat is None or lon360 is None:
                continue  # sin coordenadas: nada consultable
            # En la Luna TODOS los cráteres con nombre cuentan (política
            # lunar: el Kaguya DTM de ~10 m/px los resuelve; en Marte el
            # filtro de 40 km era por densidad/interés estructural).
            es_crater = tipo.startswith("Crater")
            if es_crater and diam is not None \
                    and diam < DIAMETRO_CRATER_MIN_KM_LUNA:
                continue
            # Gazetteer 0-360 Este -> convenio del proyecto -180..180
            lon = lon360 if lon360 <= 180.0 else lon360 - 360.0
            radio = _radio_de(diam, lat, es_crater)
            sitio_id = f"moon@{lat:.2f},{lon:.2f}±{radio:.2f}"
            con.execute(
                """INSERT OR IGNORE INTO sitios
                   (sitio_id, nombre, tipo, diametro_km, lat, lon, radio,
                    estado, actualizado)
                   VALUES (?, ?, ?, ?, ?, ?, ?, 'pendiente', ?)""",
                (sitio_id, nombre, tipo, diam, lat, lon, radio,
                 datetime.now().isoformat(timespec="seconds")))
            insertados += 1
        total = con.execute("SELECT COUNT(*) FROM sitios").fetchone()[0]
        con.commit()
    con.close()

    resumen = {
        "filas_gazetteer": len(filas),
        "nuevos_insertados": insertados,
        "excluidos_satellite_feature": excluidos,
        "total_en_db": total,
        "db": str(RUTA_DB),
    }
    _aviso("indexado: " + json.dumps(resumen, ensure_ascii=False))
    return resumen


# ---------------------------------------------------------------------------
# 3. Enriquecimiento (stats topográficos vía DTM Kaguya)
# ---------------------------------------------------------------------------

def _nota_de_cobertura(res: dict[str, Any]) -> str | None:
    """Nota honesta sobre cobertura/huecos (misma pauta que la marciana)."""
    notas = []
    cov = res.get("cobertura_fraccion")
    if isinstance(cov, (int, float)) and cov < COBERTURA_MINIMA:
        notas.append(f"el tile cubre el {round(cov * 100)}% de la caja: "
                     "las métricas describen esa fracción")
    val = res.get("pixeles_validos_fraccion")
    if isinstance(val, (int, float)) and val < PIXELES_VALIDOS_MIN:
        notas.append(f"solo {round(val * 100)}% de píxeles válidos "
                     "(huecos del DTM)")
    return "; ".join(notas) or None


def _enriquecer_sitio(fila: sqlite3.Row, aviso=None) -> dict[str, Any]:
    """Procesa UN sitio 'pendiente' y devuelve el UPDATE listo para la DB.

    Red por sitio: 1 búsqueda STAC pequeña (cacheada) + lectura remota del
    trozo Kaguya (/vsicurl, ~2-8 s). Sin térmico (ver docstring del módulo).

    POLÍTICA LUNAR RELAJADA de la criba (igual que la DB marciana):
    >=50% píxeles válidos Y >=50% cobertura; si no pasa, 'sin_dtm'
    (honesto: en la Luna el respaldo sería el GDS LOLA, minutos/sitio,
    que NO se lanza en la criba masiva).
    """
    def _aviso(msg: str) -> None:
        if aviso:
            aviso(msg)

    lat, lon, radio = fila["lat"], fila["lon"], fila["radio"]
    cambios: dict[str, Any] = {
        "sitio_id": fila["sitio_id"],
        "actualizado": datetime.now().isoformat(timespec="seconds")}
    try:
        bbox_stac = utilidades.caja_stac(lat, lon, radio)
        items = topografia.dtm_disponibles("moon", bbox_stac, lat)
        res = topografia_dtm.analizar_sitio(
            lat, lon, radio, items_stac=items, cuerpo="moon",
            modo_tile="remoto")

        sin_tile = "sin tile DEM" in str(res.get("error", ""))
        cobertura = res.get("cobertura_fraccion") or 0.0
        dtm_util = ("elevacion" in res
                    and bool(res.get("confiable", False))
                    and cobertura >= COBERTURA_MINIMA)
        if sin_tile or not dtm_util:
            cambios["estado"] = "sin_dtm"
            if sin_tile:
                cambios["error"] = str(res.get("error", ""))[:300]
            else:
                cambios["error"] = (
                    f"DTM descartado: cobertura {round(cobertura * 100)}% "
                    f"/ píxeles válidos "
                    f"{round((res.get('pixeles_validos_fraccion') or 0) * 100)}% "
                    f"< política lunar ({str(res.get('error') or '')[:120]})")
            return cambios

        elev = res["elevacion"]
        pend = res.get("pendiente") or {}
        rug = res.get("rugosidad") or {}
        crateres = res.get("crateres") or {}
        cambios.update({
            "estado": "listo",
            "error": None,
            "elevacion_min_m": elev.get("min"),
            "elevacion_media_m": elev.get("media"),
            "elevacion_max_m": elev.get("max"),
            "elevacion_mediana_m": elev.get("mediana"),
            "pendiente_media_grados": pend.get("media"),
            "rugosidad_media_m": rug.get("media") if "media" in rug else None,
            "n_pixeles": elev.get("n_pixeles"),
            "cobertura": res.get("cobertura_fraccion"),
            "resolucion_m": res.get("resolucion_m"),
            "n_crateres": crateres.get("n_candidatos"),
            "nota": _nota_de_cobertura(res),
            "tile_id": res.get("tile"),
            "tile_url": res.get("url"),
            "fuente_dtm": res.get("fuente"),
        })
        _aviso(f"  topografía OK ({res.get('resolucion_m')} m/px, "
               f"cobertura {res.get('cobertura_fraccion')})")
    except Exception as exc:  # red caída, JSON raro, lo que sea
        cambios["estado"] = "error"
        cambios["error"] = str(exc)[:300]
    return cambios


def _guardar(cambios: dict[str, Any]) -> None:
    """Escribe el UPDATE del sitio (columnas presentes en el dict)."""
    sitio_id = cambios.pop("sitio_id")
    if not cambios:
        return
    cols = ", ".join(cambios)
    set_sql = ", ".join(f"{c} = ?" for c in cambios)
    con = _conectar()
    with _LOCK_SQLITE:
        con.execute(f"UPDATE sitios SET {set_sql} WHERE sitio_id = ?",
                    (*cambios.values(), sitio_id))
        con.commit()
    con.close()


def enriquecer(max_sitios: int = 50, hilos: int = 3,
               aviso=None) -> dict[str, Any]:
    """Calcula topografía para los sitios 'pendiente' (resumible).

    Mismo contrato que el marciano: cada sitio procesado queda con
    estado en la DB; repetir continúa donde quedó. Paralelismo con
    hilos (2-3 máximo: cortesía con el STAC de USGS).
    """
    def _aviso(msg: str) -> None:
        if aviso:
            aviso(msg)

    con = _conectar()
    filas = con.execute(
        """SELECT sitio_id, nombre, lat, lon, radio FROM sitios
           WHERE estado = 'pendiente' ORDER BY sitio_id LIMIT ?""",
        (max_sitios,)).fetchall()
    con.close()
    if not filas:
        _aviso("no hay sitios 'pendiente' (¿ya está todo enriquecido?)")
        return {"procesados": 0}

    t0 = time.perf_counter()
    contadores: dict[str, Any] = {"listo": 0, "sin_dtm": 0, "error": 0}

    def _procesar(fila: sqlite3.Row) -> None:
        _aviso(f"{fila['nombre']} ({fila['lat']:.2f}, {fila['lon']:.2f})...")
        cambios = _enriquecer_sitio(fila, aviso=_aviso)
        _guardar(cambios)
        contadores[cambios["estado"]] = \
            contadores.get(cambios["estado"], 0) + 1

    with ThreadPoolExecutor(max_workers=max(1, min(hilos, 3))) as pool:
        futuros = [pool.submit(_procesar, f) for f in filas]
        for f in as_completed(futuros):
            f.result()  # propaga excepciones no capturadas (no debería)

    contadores["segundos"] = round(time.perf_counter() - t0, 1)
    con = _conectar()
    contadores["restantes_pendientes"] = con.execute(
        "SELECT COUNT(*) FROM sitios WHERE estado = 'pendiente'"
    ).fetchone()[0]
    con.close()
    _aviso("enriquecido: " + json.dumps(contadores, ensure_ascii=False))
    return contadores


# ---------------------------------------------------------------------------
# 4. Consulta en el formato de comparación del proyecto
# ---------------------------------------------------------------------------

def sitios_disponibles(n: int | None = None, tipo: str | None = None,
                       solo_listos: bool = True) -> list[dict[str, Any]]:
    """Sitios con datos, en el formato de comparación del proyecto.

    Cada dict replica las claves del 'resumen' del registro de
    `obtener_datos_sitio()` (solo las que tienen dato) + metadatos de la
    DB (nombre, tipo). `via_topografia='dtm_kaguya'`, alias n_puntos_lola
    = n_pixeles (alias histórico del proyecto).
    """
    sql = """SELECT * FROM sitios
             WHERE (? = 0 OR estado = 'listo')
               AND (? IS NULL OR tipo LIKE ?)
             ORDER BY nombre"""
    con = _conectar()
    filas = con.execute(
        sql, (1 if solo_listos else 0, tipo,
              f"%{tipo}%" if tipo else None)).fetchall()
    con.close()
    if n:
        filas = filas[:n]

    out = []
    for f in filas:
        resumen: dict[str, Any] = {}
        if f["elevacion_media_m"] is not None:
            resumen["elevacion_media_m"] = f["elevacion_media_m"]
        if f["pendiente_media_grados"] is not None:
            resumen["pendiente_media_grados"] = f["pendiente_media_grados"]
        if f["rugosidad_media_m"] is not None:
            resumen["rugosidad_media_m"] = f["rugosidad_media_m"]
        if f["n_pixeles"] is not None:
            resumen["n_puntos_lola"] = f["n_pixeles"]  # alias histórico
        resumen["via_topografia"] = "dtm_kaguya"

        extra: dict[str, Any] = {}
        for clave in ("elevacion_min_m", "elevacion_max_m",
                      "elevacion_mediana_m", "resolucion_m", "cobertura",
                      "n_crateres", "nota", "fuente_dtm", "tile_id"):
            if f[clave] is not None:
                extra[clave] = f[clave]

        out.append({
            "sitio_id": f["sitio_id"],
            "nombre": f["nombre"],
            "tipo": f["tipo"],
            "diametro_km": f["diametro_km"],
            "lat": round(f["lat"], 4),
            "lon": round(f["lon"], 4),
            "radio_grados": round(f["radio"], 3),
            "resumen": resumen,
            "topografia_extra": extra,
            "actualizado": f["actualizado"],
        })
    return out


def estado_db() -> dict[str, Any]:
    """Conteos por estado (para el comando 'estado')."""
    con = _conectar()
    por_estado = dict(con.execute(
        "SELECT estado, COUNT(*) FROM sitios GROUP BY estado").fetchall())
    tipos = con.execute(
        "SELECT tipo, COUNT(*) FROM sitios GROUP BY tipo "
        "ORDER BY COUNT(*) DESC").fetchall()
    con.close()
    return {
        "db": str(RUTA_DB),
        "por_estado": por_estado,
        "por_tipo": {t[0]: t[1] for t in tipos},
        "total": sum(por_estado.values()),
    }


# ---------------------------------------------------------------------------
# 5. CLI
# ---------------------------------------------------------------------------

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

    parser = argparse.ArgumentParser(
        description="DB local de sitios LUNARES (Gazetteer + DTM Kaguya). "
                    "Ver docstring del módulo.")
    sub = parser.add_subparsers(dest="comando", required=True)
    sub.add_parser("indexar",
                   help="descarga el Gazetteer y crea los 'pendiente'")
    p_enr = sub.add_parser(
        "enriquecer", help="calcula stats para los 'pendiente' (resumible)")
    p_enr.add_argument("--max", type=int, default=50)
    p_enr.add_argument("--hilos", type=int, default=3)
    p_list = sub.add_parser("listar", help="sitios con datos")
    p_list.add_argument("--n", type=int, default=15)
    p_list.add_argument("--tipo", default=None)
    p_list.add_argument("--todos", action="store_true")
    sub.add_parser("reintentar", help="'error' vuelve a 'pendiente'")
    sub.add_parser("estado", help="conteos por estado y tipo")
    args = parser.parse_args()

    if args.comando == "indexar":
        indexar_gazetteer(aviso=_aviso)
    elif args.comando == "enriquecer":
        enriquecer(max_sitios=args.max, hilos=args.hilos, aviso=_aviso)
    elif args.comando == "listar":
        lista = sitios_disponibles(n=args.n, tipo=args.tipo,
                                   solo_listos=not args.todos)
        print(json.dumps(lista, ensure_ascii=False, indent=1))
    elif args.comando == "reintentar":
        con = _conectar()
        cur = con.execute(
            "UPDATE sitios SET estado='pendiente', error=NULL "
            "WHERE estado='error'")
        con.commit()
        con.close()
        _aviso(f"{cur.rowcount} sitios vueltos a 'pendiente'")
    elif args.comando == "estado":
        print(json.dumps(estado_db(), ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
