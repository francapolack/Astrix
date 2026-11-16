"""Térmica — temperatura superficial de Diviner (Luna) con UNA consulta.

Diviner (a bordo del LRO) mide en 9 canales:
  - canales 1-2: SOLARES (0.3-0.6 µm) -> luz solar REFLEJADA (≈ albedo).
  - canales 3-9: TÉRMICOS (7.55-200 µm) -> temperatura de brillo (K).

Estrategia de eficiencia: pedimos TODOS los canales a la vez
(`channel="fffffffff"`, 9 banderas) en UNA sola consulta GDS. De ese único
CSV salen:
  - temperatura media / máxima / mínima        (canales 3-9)
  - diferencia día-noche                        (ángulo cenital solar)
  - variación estacional                        (fecha de cada observación)
  - reflectancia/albedo                         (canales 1-2)
La función `datos_diviner` devuelve TODO eso; `api.py` reparte el resultado
entre las secciones 'termico' y 'superficie' del diccionario final.
"""

from __future__ import annotations

from typing import Any

from . import utilidades


def datos_diviner(cajas: list[tuple[float, float, float, float]]) -> dict[str, Any]:
    """Consulta GDS de Diviner (1 llamada por caja) y resume todo el CSV.

    Devuelve un dict con las claves:
      'temperatura_superficial' -> {media, max, min, ...} en K (canales 3-9)
      'dia_noche'               -> {media_dia_k, media_noche_k, diferencia_k}
      'variacion_estacional'    -> {media_por_mes, variacion_k} (o None + nota)
      'reflectancia_albedo'     -> estadísticas de los canales 1-2
      'errores'                 -> texto si alguna caja falló
    """
    import pandas as pd
    from . import cache_gds

    # --- 1) una consulta GDS por caja (normalmente solo hay una) ----------
    # Cada CSV pasa por la caché local: la primera vez se baja del GDS y se
    # guarda; las siguientes se leen del disco en milisegundos.
    frames: list[Any] = []
    errores: list[str] = []
    for caja in cajas:
        try:
            # channel="fffffffff": las 9 banderas a False = pedimos los 9
            # canales. (El preset de nsac trae "ffttttttt" = solo térmicos;
            # con 'f' también llegan los solares y así ahorrarnos otra llamada.)
            df_caja, _ruta, _cache = cache_gds.leer_o_descargar(
                "divinerrdr", caja, channel="fffffffff")
            frames.append(df_caja)
        except Exception as exc:
            errores.append(f"caja {caja}: {exc}")

    if not frames:
        return {"error": "; ".join(errores) or "sin datos"}

    df = pd.concat(frames, ignore_index=True)

    # --- 2) localizar columnas por significado ----------------------------
    # El canal se llama exactamente 'c' en el CSV del GDS; buscamos primero
    # esa coincidencia exacta y, si no, nombres alternativos ('channel').
    # No usamos columna_con(df, ["c"]) porque 'clat'/'csunzen' también
    # contienen la letra 'c' y podrían casar antes.
    col_canal = "c" if "c" in df.columns else utilidades.columna_con(
        df, ["channel", "schannel"])
    col_tb = utilidades.columna_con(df, ["tb", "temp"])    # temperatura/valor
    if col_canal is None or col_tb is None:
        return {"error": f"columnas inesperadas: {list(df.columns)}"}

    canal = pd.to_numeric(df[col_canal], errors="coerce")
    valor = pd.to_numeric(df[col_tb], errors="coerce")

    # --- 3) TEMPERATURA (canales térmicos 3-9) ----------------------------
    # Filtramos al rango físico razonable (20-400 K): fuera quedan píxeles
    # malos o filas de los canales solares que se colaron.
    m_term = (canal >= 3) & (canal <= 9) & (valor > 20) & (valor < 400)
    resumen: dict[str, Any] = {
        "fuente": "LRO Diviner RDR vía PDS GDS (canales 3-9 térmicos)",
        "n_observaciones": int(m_term.sum()),
        "temperatura_superficial": utilidades.estadisticas(
            [float(v) for v in valor[m_term].dropna()]),
        "errores": errores,
    }

    df_term = df[m_term].copy()
    df_term["tb_num"] = valor[m_term]

    # --- 4) DÍA / NOCHE con el ángulo cenital solar ------------------------
    # csunzen < 90° -> el Sol está sobre el horizonte (día); >= 90° -> noche.
    col_zen = utilidades.columna_con(df, ["csunzen", "sunzen"])
    if col_zen is not None:
        zen = pd.to_numeric(df_term[col_zen], errors="coerce")
        tb_dia = df_term.loc[zen < 90, "tb_num"]
        tb_noche = df_term.loc[zen >= 90, "tb_num"]
        mdia = float(tb_dia.mean()) if len(tb_dia) else None
        mnoche = float(tb_noche.mean()) if len(tb_noche) else None
        if mdia is not None and mnoche is not None:
            resumen["dia_noche"] = {
                "media_dia_k": round(mdia, 2),
                "media_noche_k": round(mnoche, 2),
                "diferencia_k": round(mdia - mnoche, 2),
                "metodo": "csunzen<90 = día; >=90 = noche (Diviner)",
            }
        # Guardamos los ángulos crudos para que `iluminacion.fraccion_diurna`
        # pueda reutilizarlos SIN una segunda descarga (clave interna que
        # api.py elimina del resultado final).
        resumen["_angulos_solares"] = [float(v) for v in zen.dropna()]

    # --- 5) VARIACIÓN ESTACIONAL por fecha --------------------------------
    # El GDS escribe las fechas como '01-Dec-2009'. Las convertimos a fecha
    # real y agrupamos la temperatura media por MES DEL AÑO (01..12): para la
    # Luna, el mes del año es la "estación" porque tarda ~1 año terrestre en
    # rodear el Sol.
    col_fecha = utilidades.columna_con(df, ["date", "scet", "utc", "start_time"])
    if col_fecha is not None:
        fecha = pd.to_datetime(df_term[col_fecha], errors="coerce",
                               format="mixed", dayfirst=True)
        df_term["mes"] = fecha.dt.month  # 1..12; NaN si la fecha no se pudo leer
        medias_mes = (df_term.dropna(subset=["mes"])
                      .groupby("mes")["tb_num"].mean().sort_index())
        if len(medias_mes) >= 2:
            resumen["variacion_estacional"] = {
                "media_por_mes_k": {f"{int(m):02d}": round(float(v), 1)
                                    for m, v in medias_mes.items()},
                "variacion_k": round(float(medias_mes.max() - medias_mes.min()), 2),
                "nota": "media por mes del año (01=enero ... 12=diciembre): "
                        "la Luna tarda ~1 año terrestre en rodear el Sol, "
                        "así que estos 12 valores son su ciclo estacional",
            }
        else:
            resumen["variacion_estacional"] = {
                "nota": (f"solo {len(medias_mes)} mes(es) con datos en esta "
                         "caja: para ver la variación estacional se necesita "
                         "una caja más amplia o varias fechas")
            }
    else:
        resumen["variacion_estacional"] = {
            "nota": "el GDS no devolvió columna de fecha para esta caja"}

    # --- 6) REFLECTANCIA / ALBEDO (canales solares 1-2) --------------------
    # En estos canales la columna 'tb' no es temperatura sino radianza solar
    # reflejada; su valor (normalmente 0-1.5) aproxima la reflectancia.
    m_sol = (canal <= 2) & (valor >= 0) & (valor <= 1.5)
    refl = utilidades.estadisticas([float(v) for v in valor[m_sol].dropna()])
    if refl:
        refl["nota"] = ("canales solares 1-2 de Diviner (0.3-0.6 µm): valor "
                        "≈ reflectancia de la superficie")
    resumen["reflectancia_albedo"] = refl

    return resumen
