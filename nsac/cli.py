"""CLI de exploración: python -m nsac.cli <comando> [opciones]

Ejemplos:
    python -m nsac.cli doctor
    python -m nsac.cli earth search --keyword "land surface temperature"
    python -m nsac.cli pds bundles --keyword diviner
    python -m nsac.cli moon ode --iid LOLA --pt RDR4 --bbox -90,-85,-180,180
    python -m nsac.cli moon gds --query divinerrdr --bbox -89.6,-89,0,1
    python -m nsac.cli trek layers --body moon --keyword PSR
    python -m nsac.cli stac --collection kaguya_terrain_camera_usgs_dtms_v2_southpolar
    python -m nsac.cli csa regions
    python -m nsac.cli csa scenes --region "Canadian Arctic"
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any, Callable

from .sources import asf, copernicus, csa, earthcode, earthdata, jaxa, pds, trek, usgs_stac


# ------------------------------------------------------------------ utilidades
def bbox_arg(text: str) -> tuple[float, float, float, float]:
    parts = [float(p) for p in text.replace(" ", "").split(",")]
    if len(parts) != 4:
        raise argparse.ArgumentTypeError("bbox debe ser 'a,b,c,d'")
    return (parts[0], parts[1], parts[2], parts[3])


def dump(rows: Any, limit: int = 20) -> None:
    rows = rows if isinstance(rows, list) else [rows]
    for row in rows[:limit]:
        print(json.dumps(row, ensure_ascii=False, indent=2, default=str))
    if len(rows) > limit:
        print(f"... ({len(rows)} resultados, mostrando {limit})")


# ------------------------------------------------------------------- comandos
def cmd_doctor(_: argparse.Namespace) -> None:
    """Comprueba en vivo qué fuentes responden desde tu red."""
    checks: list[tuple[str, Callable[[], Any]]] = [
        ("NASA CMR (Earth)", lambda: earthdata.search_collections("SMAP", page_size=1)),
        ("NASA GIBS (Worldview)", lambda: earthdata.search_gibs_layers("TrueColor")[:1]),
        ("PDS Search API", lambda: len(pds.search_bundles("lro"))),
        ("PDS listado HTTP", lambda: len(pds.list_dir(pds.latest_rdr_dir()))),
        ("ODE REST (LRO)", lambda: pds.ode_products("LRO", "LOLA", "RDR4", limit=1)["count"]),
        ("USGS STAC", lambda: len(usgs_stac.collections())),
        ("Copernicus STAC", lambda: len(copernicus.search_stac(["sentinel-2-l1c"], limit=1))),
        ("ESA EarthCODE", lambda: len(earthcode.collections(limit=1))),
        ("CSA CKAN", lambda: len(csa.ckan_search("RCM", rows=1))),
        ("CSA RCM abierto", lambda: len(csa.rcm_regions())),
        ("CSA EODMS", lambda: len(csa.eodms_collections())),
        ("ASF (SAR)", lambda: len(asf.search(platform="Sentinel-1", max_results=1))),
        ("NASA Treks (Luna)", lambda: len(trek.layers("moon"))),
        ("JAXA G-Portal", lambda: jaxa.check()["credenciales"]),
    ]
    ok = 0
    for name, fn in checks:
        try:
            value = fn()
            ok += 1
            print(f"  OK   {name:24} -> {value}")
        except Exception as exc:  # noqa: BLE001
            print(f"  FAIL {name:24} -> {type(exc).__name__}: {exc}")
    print(f"\n{ok}/{len(checks)} fuentes responden.")


def main(argv: list[str] | None = None) -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    p = argparse.ArgumentParser(
        prog="nsac", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    p_doctor = sub.add_parser("doctor", help="comprueba todas las fuentes")
    p_doctor.set_defaults(fn=cmd_doctor)

    # --- earth
    earth = sub.add_parser("earth", help="NASA Earthdata (CMR / GIBS)")
    earth_sub = earth.add_subparsers(dest="sub", required=True)

    e = earth_sub.add_parser("search", help="busca colecciones en CMR")
    e.add_argument("--keyword", required=True)
    e.add_argument("--limit", type=int, default=10)
    e.set_defaults(fn=lambda a: dump(earthdata.search_collections(a.keyword, page_size=a.limit), a.limit))

    e = earth_sub.add_parser("granules", help="busca archivos de una colección")
    e.add_argument("--concept-id", required=True)
    e.add_argument("--bbox", type=bbox_arg)
    e.add_argument("--limit", type=int, default=10)
    e.set_defaults(fn=lambda a: dump(earthdata.search_granules(a.concept_id, a.bbox, page_size=a.limit), a.limit))

    e = earth_sub.add_parser("gibs", help="lista capas de teselas GIBS")
    e.add_argument("--keyword", default="")
    e.set_defaults(fn=lambda a: dump(earthdata.search_gibs_layers(a.keyword), 40))

    # --- pds
    pds_cmd = sub.add_parser("pds", help="Planetary Data System")
    pds_sub = pds_cmd.add_subparsers(dest="sub", required=True)

    q = pds_sub.add_parser("bundles", help="busca bundles PDS4 por texto")
    q.add_argument("--keyword", default=None)
    q.add_argument("--limit", type=int, default=20)
    q.set_defaults(fn=lambda a: dump(pds.search_bundles(a.keyword), a.limit))

    q = pds_sub.add_parser("collections", help="busca colecciones PDS4 por texto")
    q.add_argument("--keyword", default=None)
    q.add_argument("--limit", type=int, default=20)
    q.set_defaults(fn=lambda a: dump(pds.search_collections(a.keyword), a.limit))

    q = pds_sub.add_parser("members", help="hijos de un bundle/colección")
    q.add_argument("lidvid")
    q.add_argument("--limit", type=int, default=20)
    q.set_defaults(fn=lambda a: dump(pds.members(a.lidvid, a.limit), a.limit))

    q = pds_sub.add_parser("dir", help="lista un directorio de PDS Geosciences")
    q.add_argument("--url", default=None, help="por defecto: último release de Diviner RDR")
    q.add_argument("--limit", type=int, default=20)
    q.set_defaults(fn=lambda a: dump(pds.list_dir(a.url or pds.latest_rdr_dir()), a.limit))

    # --- moon / mars
    mm = sub.add_parser("moon", help="Luna y Marte (ODE/GDS del PDS)")
    mm_sub = mm.add_subparsers(dest="sub", required=True)

    q = mm_sub.add_parser("ode", help="productos con metadatos por bbox")
    q.add_argument("--ihid", default="LRO")
    q.add_argument("--iid", default="LOLA")
    q.add_argument("--pt", default="RDR4")
    q.add_argument("--target", default="moon")
    q.add_argument("--bbox", type=bbox_arg, default=None)
    q.add_argument("--limit", type=int, default=3)
    q.set_defaults(
        fn=lambda a: dump(pds.ode_products(a.ihid, a.iid, a.pt, a.target, a.bbox, a.limit), a.limit)
    )

    q = mm_sub.add_parser("gds", help="extrae datos LOLA/Diviner por bbox")
    q.add_argument("--query", default="divinerrdr", choices=sorted(pds.GDS_PRESETS))
    q.add_argument("--bbox", type=bbox_arg, required=True)
    q.set_defaults(fn=lambda a: dump(pds.gds_query(a.query, a.bbox), 1))

    q = mm_sub.add_parser("iipt", help="combinaciones válidas host/instrumento/producto")
    q.add_argument("--filter", default="LRO")
    q.set_defaults(
        fn=lambda a: dump([i for i in pds.ode_iipt() if a.filter in str(i.get("IHID", ""))], 60)
    )

    # --- trek
    trek_cmd = sub.add_parser("trek", help="NASA Solar System Treks (teselas)")
    trek_sub = trek_cmd.add_subparsers(dest="sub", required=True)

    q = trek_sub.add_parser("layers")
    q.add_argument("--body", default="moon")
    q.add_argument("--keyword", default="")
    q.add_argument("--projtype", default="polar", choices=["polar", "eq"])
    q.set_defaults(fn=lambda a: dump(trek.find_layers(a.keyword, a.body, a.projtype), 30))

    q = trek_sub.add_parser("tile", help="URL de una tesela concreta")
    q.add_argument("--body", default="moon")
    q.add_argument("--layer", required=True)
    q.add_argument("--zoom", type=int, default=2)
    q.add_argument("--row", type=int, default=0)
    q.add_argument("--col", type=int, default=0)
    q.set_defaults(fn=lambda a: print(trek.tile_url(a.body, a.layer, a.zoom, a.row, a.col)))

    # --- stac
    stac = sub.add_parser("stac", help="STAC de USGS Astrogeology")
    stac.add_argument("--collection", default=None)
    stac.add_argument("--bbox", type=bbox_arg, default=None)
    stac.add_argument("--limit", type=int, default=5)
    stac.add_argument("--list", action="store_true", help="lista colecciones disponibles")
    stac.set_defaults(
        fn=lambda a: dump(
            usgs_stac.collections()
            if a.list
            else usgs_stac.search([a.collection] if a.collection else None, a.bbox, limit=a.limit),
            a.limit,
        )
    )

    # --- csa
    csa_cmd = sub.add_parser("csa", help="CSA: RCM / RADARSAT")
    csa_sub = csa_cmd.add_subparsers(dest="sub", required=True)

    q = csa_sub.add_parser("regions", help="regiones del dataset abierto RCM")
    q.set_defaults(fn=lambda a: dump(csa.rcm_regions(), 50))

    q = csa_sub.add_parser("scenes", help="escenas RCM de una región")
    q.add_argument("--region", default="Canadian Arctic")
    q.add_argument("--limit", type=int, default=5)
    q.set_defaults(fn=lambda a: dump(csa.rcm_scenes(a.region), a.limit))

    # --- copernicus
    cop = sub.add_parser("copernicus", help="Copernicus Data Space (STAC)")
    cop.add_argument("--collection", default="sentinel-2-l1c")
    cop.add_argument("--bbox", type=bbox_arg, default=None)
    cop.add_argument("--limit", type=int, default=5)
    cop.set_defaults(
        fn=lambda a: dump(copernicus.search_stac([a.collection], a.bbox, limit=a.limit), a.limit)
    )

    # --- earthcode
    ec = sub.add_parser("earthcode", help="ESA Open Science Data (STAC)")
    ec.add_argument("--limit", type=int, default=20)
    ec.set_defaults(fn=lambda a: dump(earthcode.collections(a.limit), a.limit))

    # --- asf
    asf_cmd = sub.add_parser("asf", help="ASF SAR")
    asf_cmd.add_argument("--platform", default="Sentinel-1")
    asf_cmd.add_argument("--bbox", type=bbox_arg, default=None)
    asf_cmd.add_argument("--limit", type=int, default=3)
    asf_cmd.set_defaults(
        fn=lambda a: dump(asf.search(platform=a.platform, bbox=a.bbox, max_results=a.limit), a.limit)
    )

    args = p.parse_args(argv)
    args.fn(args)


if __name__ == "__main__":
    main()
