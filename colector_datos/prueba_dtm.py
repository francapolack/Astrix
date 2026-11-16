"""prueba_dtm.py — corrida del EXPERIMENTO A (rama dtm-rasterio).

Uso (desde la raíz del repo):
    python -X utf8 -m colector_datos.prueba_dtm --lat -23.4 --lon 157.8 --radio 0.05

Baja el tile Kaguya TC DEM que cubra la caja, calcula elevación/pendiente/
rugosidad sobre la MATRIZ y compara con los números de la vía GDS (LOLA)
guardados en data/registro_sitios.json para el mismo sitio. La comparación
se imprime con la diferencia relativa, porque las dos fuentes NO deben dar
exactamente lo mismo (distinta misión, distinta resolución) pero sí el
mismo orden de magnitud y la misma lectura operativa (¿llano o escarpado?).
"""

from __future__ import annotations

import argparse
import json

from . import topografia_dtm


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Piloto DTM (rasterio) con comparación vs LOLA/GDS.")
    parser.add_argument("--lat", type=float, required=True)
    parser.add_argument("--lon", type=float, required=True)
    parser.add_argument("--radio", type=float, required=True)
    parser.add_argument("--cuerpo", default="luna", choices=("luna", "marte"),
                        help="cuerpo del sitio (por defecto: luna)")
    args = parser.parse_args()

    cuerpo = "mars" if args.cuerpo == "marte" else "moon"

    def _aviso(msg: str) -> None:
        print(f"  · {msg}", flush=True)

    print("=" * 70)
    print(f"EXPERIMENTO A — DTM por rasterio  ({args.cuerpo} {args.lat}, "
          f"{args.lon}, ±{args.radio})")
    print("=" * 70)

    res = topografia_dtm.analizar_sitio(args.lat, args.lon, args.radio,
                                        aviso=_aviso, cuerpo=cuerpo)

    if "error" in res:
        print(f"\nRESULTADO: FALLÓ -> {res['error']}")
        print(f"Fallback previsto: vía GDS LOLA ({res.get('fallback')})")
        return

    print(f"\nTiempos:  STAC {res['stac_s']} s  +  descarga {res['descarga_s']} s"
          f"  +  cómputo {res['computo_s']} s  =  TOTAL {res['total_s']} s"
          f"  (tile {'en caché' if res.get('de_cache') else 'descargado'})")
    print(f"Tile: {res['tile']}")
    print(f"Cobertura de la caja por el tile: {res['cobertura_fraccion'] * 100:.0f} %"
          f" · píxeles válidos dentro: {res['pixeles_validos_fraccion'] * 100:.0f} %")
    print(f"Resolución: ~{res['resolucion_m']} m/píxel")

    elev = res["elevacion"]
    print(f"\nElevación (m): min {elev['min']} · media {elev['media']} · "
          f"mediana {elev['mediana']} · max {elev['max']} · "
          f"desv {elev['desv_estandar']}"
          f"  ({elev['n']} píxeles)")
    pen = res["pendiente"]
    print(f"Pendiente (grados): media {pen['media']} · mediana {pen['mediana']}"
          f" · max {pen['max']}  ({pen['n']} px)")
    rug = res["rugosidad"]
    if "nota" in rug:
        print(f"Rugosidad: {rug['nota']}")
    else:
        print(f"Rugosidad (m, celdas de {rug.get('tamano_celda_m', 100):.0f} m): "
              f"media {rug['media']} · mediana {rug['mediana']} · max {rug['max']}"
              f"  ({rug['n_celdas_100m']} celdas)")

    # --- comparación con la vía GDS (LOLA) del registro -------------------
    clave = f"moon@{args.lat},{args.lon}±{args.radio}"
    try:
        registro = json.load(open(
            topografia_dtm.constantes.RUTA_REGISTRO, encoding="utf-8"))
        base = registro.get(clave, {}).get("resumen", {})
    except Exception:
        base = {}

    if not base or "elevacion_media_m" not in base:
        print("\n(No hay línea base LOLA en el registro para esta clave —"
              " nada que comparar.)")
        return

    print("\nCOMPARACIÓN CON LA VÍA GDS (LOLA, mismo sitio):")
    filas = [
        ("elevación media (m)", elev["media"], base["elevacion_media_m"]),
        ("pendiente media (°)", pen["media"], base["pendiente_media_grados"]),
        ("rugosidad media (m)",
         rug.get("media"), base["rugosidad_media_m"]),
    ]
    for nombre, dtm, lola in filas:
        if dtm is None or lola in (None, 0):
            print(f"  {nombre:24s} dtm={dtm}  lola={lola}")
            continue
        dif = abs(dtm - lola)
        rel = dif / max(abs(lola), 1e-9) * 100
        print(f"  {nombre:24s} dtm={dtm:10.3f}  lola={lola:10.3f}  "
              f"Δabs={dif:.3f}  Δrel={rel:.1f} %")


if __name__ == "__main__":
    main()
