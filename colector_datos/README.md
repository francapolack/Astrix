# colector_datos — un diccionario con todos los parámetros del sitio

Paquete independiente del resto del proyecto que, con **una sola llamada de
función**, devuelve un diccionario de Python con los parámetros del reto,
consultando las fuentes que ya trae el paquete `nsac` (PDS, USGS STAC, Treks,
CMR, Copernicus).

```python
from colector_datos import obtener_datos_sitio

datos = obtener_datos_sitio(cuerpo="luna", lat=-89.9, lon=0.05, radio=0.05)

datos["topografia"]["elevacion_m"]        # {min, max, media, mediana, ...}
datos["termico"]["temperatura_superficial"]
datos["superficie"]["reflectancia_albedo"]
datos["iluminacion"]["zonas_sombra_psr"]
```

## Cómo se mapea cada parámetro (qué archivo lo trae)

| Parámetro pedido | Módulo | Fuente | ¿Cuántas llamadas? |
|---|---|---|---|
| Elevación | `topografia_dtm.py` / `topografia.py` | **DTM Kaguya (GeoTIFF vía rasterio)** si el tile cubre la caja; si no, LOLA por PDS GDS (respaldo) | 1 STAC + 1 tile (o 1 GDS) |
| Pendiente del terreno | `topografia_dtm.py` / `topografia.py` | **calculada en local** (gradiente sobre la malla DTM, o pares de celdas sobre los puntos LOLA) | 0 extra |
| Rugosidad superficial | `topografia_dtm.py` / `topografia.py` | **calculada en local** (desv. típica por celdas de ~100 m) | 0 extra |
| Cráteres / formaciones geológicas | `topografia_dtm.py` / `topografia.py` | **calculado en local** (depresiones vs vecinas, sobre malla o nube) + mapa geológico USGS + capas Treks | 0 extra |
| Temperatura media, máx y mín | `termico.py` | Diviner por PDS GDS | 1 GDS |
| Diferencia térmica día/noche | `termico.py` | mismo CSV Diviner (ángulo cenital solar) | 0 extra |
| Variación estacional | `termico.py` | mismo CSV Diviner (agrupando por mes) | 0 extra |
| Tipo de roca | `superficie.py` | heurística sobre el albedo de Diviner | 0 extra |
| Minerales predominantes | `superficie.py` | capas Treks + bundles Clementine (PDS) | 1 PDS |
| Reflectancia y albedo | `termico.py`→`superficie.py` | canales solares 1-2 de Diviner | 0 extra |
| Materiales superficiales y polvo | `superficie.py` | capas Treks (parámetro H / regolito) | 0 extra |
| Horas de iluminación | `iluminacion.py` | capas Treks (LOLA/Kaguya illumination) | 0 extra |
| Energía solar recibida | `iluminacion.py` | cálculo local: E = 1361 W/m² × fracción iluminada | 0 extra |
| Variaciones de exposición solar | `iluminacion.py` | capas Treks + fechas de Diviner | 0 extra |
| Zonas en sombra permanente (PSR) | `iluminacion.py` | capas Treks (PSR) + fracción diurna de Diviner | 0 extra |
| (lado Tierra) | `analogos_tierra.py` | CMR + GIBS + Copernicus | opcional, ~6 |

**Total Luna: ~5 llamadas HTTP** con `usar_dtm=True` (1 STAC + 1 tile Kaguya
~7 MB dan la topografía completa; el GDS LOLA ni se consulta) y **1 sola
consulta GDS** (Diviner, que puede tardar minutos). Todo lo cacheado
(catálogos, tiles, CSV GDS) sale del disco en las corridas siguientes.

## Archivos

```
colector_datos/
  __init__.py          expone obtener_datos_sitio()
  api.py               ← la función principal que une todo (paraleliza y decide vía DTM/LOLA)
  constantes.py        constantes físicas, sitios de ejemplo, palabras clave
  utilidades.py        pendiente, rugosidad, cráteres, distancias, estadísticas
  topografia.py        elevación LOLA (GDS), catálogo DTM (STAC), capas Treks
  topografia_dtm.py    EXPERIMENTO A: topografía desde DTM (Kaguya en Luna,
                       CTX/HiRISE en Marte) con rasterio
  termico.py           Diviner: temperatura + día/noche + estacional + albedo
  superficie.py        tipo de roca, minerales, polvo/regolito
  iluminacion.py       iluminación, energía solar, PSR
  analogos_tierra.py   el lado terrestre de la comparación (CMR/GIBS/S2)
  cache_gds.py         caché local de los CSV del GDS (Diviner/LOLA)
  cache_catalogo.py    caché local de catálogos (Treks, STAC)
  db_sitios_marte.py   DB local de sitios marcianos con nombre (Gazetteer
                       + DTM remoto + ventana THEMIS): el menú de sitios
                       con datos reales para ofrecer al usuario
  ejemplo_uso.py       script de muestra ejecutable
  prueba_funcion.py    informe legible de un sitio (--sin_dtm para vía LOLA)
  prueba_tierra.py     informe de análogos terrestres
  prueba_dtm.py        corrida del experimento A con comparación vs LOLA
  NOTAS_NOCTURNAS.md   mediciones, veredictos y decisiones (leer antes de mergear)
```

## Cómo ejecutar

Desde la raíz del proyecto (donde está `pyproject.toml`):

```powershell
python -m colector_datos.ejemplo_uso              # Shackleton (polo sur lunar)
python -m colector_datos.ejemplo_uso --rapido     # sin GDS (responde en segundos)
python -m colector_datos.ejemplo_uso --marte      # Jezero (Marte)
python -m colector_datos.ejemplo_uso --sitio peary

python -m colector_datos.prueba_funcion --sitio malapert      # informe completo + explicación
python -m colector_datos.prueba_funcion --lat 41.2 --lon -23.7 --sin_dtm  # vía LOLA (A/B)
python -m colector_datos.prueba_dtm --lat -23.4 --lon 157.8 --radio 0.05  # piloto DTM vs LOLA
```

O desde tu propia aplicación:

```python
from colector_datos import obtener_datos_sitio

# Sitio polar lunar, con teselas para el visor y análogos terrestres:
datos = obtener_datos_sitio(
    cuerpo="luna", lat=-89.9, lon=0.05, radio=0.05,
    con_teselas=True,        # URLs WMTS listas para Leaflet/MapLibre (+llamadas)
    incluir_tierra=True,     # sección de datos terrestres (~6 llamadas más)
)

# MARTE: mismas secciones y MISMAS claves que la Luna, para comparar cuerpos.
datos = obtener_datos_sitio(cuerpo="marte", lat=18.38, lon=77.58, radio=0.5)
datos["topografia"]["elevacion_m"]["media"]   # -2377.9 (piso del cráter Jezero)
datos["topografia"]["via"]                    # 'dtm_mro' (DTM CTX vía rasterio)
```

## Marte (qué fuente trae cada parámetro)

Marte NO tiene LOLA ni Diviner (instrumentos de la LRO, lunar). El colector
usa las fuentes marcianas equivalentes y devuelve el MISMO formato de
diccionario:

| Parámetro | Fuente marciana | Nota |
|---|---|---|
| Elevación / pendiente / rugosidad / cráteres | **DTM de MRO CTX/HiRISE** (USGS STAC, tile GeoTIFF vía rasterio, ~20 m/px) | Misma receta que el DTM Kaguya lunar; CRS marciana IAU_2015:499xx (equirectangular en metros) resuelta con la fórmula manual. Política de cobertura ≥50 % (sin fallback GDS: en Marte no existe LOLA) y `nota_cobertura` cuando el tile no cubre todo |
| Temperatura | **Ninguna puntual**: capas THEMIS/TES de Mars Trek + instrucciones de PDS ODE | No hay servicio tipo GDS marciano (verificado: los presets `mola*`/`themisrdr`/`mgs_tes` del GDS lunares son rechazados con 'include a query type') |
| Minerales / superficie | capas Mars Trek (CRISM/Ω/TES) | mismo formato `superficie` que la Luna |
| Iluminación / energía solar | capas Mars Trek + cálculo local | mismo formato `iluminacion` |
| `resumen` del registro | idénticas claves, `via_topografia='dtm_mro'` | comparación Luna↔Marte directa |

Sitios marcianos con DTM controlado en el STAC: **Jezero** (y demás zonas de
misión cubiertas por los DTMs controlados de CTX/HiRISE). Sitios SIN tiles
(p.ej. Gale): la sección topográfica queda en catálogos con
`nota_elevacion` explicando cómo descargar el DTM de PDS ODE — nunca se
inventan números.

### DB de sitios disponibles (`db_sitios_marte.py`)

Para no adivinar qué sitios tienen datos, hay una DB local (SQLite,
`data/db/sitios_marte.db`, gitignored como las cachés) que indexa los
**1.133 lugares con nombre** del Gazetteer IAU/USGS de Marte (cráteres
≥ 40 km + montes, valles, planicies, pateras...) y, por cada uno:

- **Topografía** en el MISMO `resumen` del registro
  (`elevacion_media_m`, `pendiente_media_grados`, `rugosidad_media_m`,
  `n_puntos_lola` = píxeles, `via_topografia='dtm_mro'`), calculada SIN
  descargar tiles (lectura remota `/vsicurl` del trozo del GeoTIFF del
  STAC). Solo pasa a 'listo' un sitio que cumpla la misma política que
  `obtener_datos_sitio` (cobertura ≥ 50 %); el resto queda 'sin_dtm' con
  el motivo — la DB refleja la cobertura real de los DTM controlados.
- **THEMIS** (mediciones múltiples): metadatos de disponibilidad — cuántas
  observaciones IRBTR4 hay en la caja (ODE) y el detalle de las de la
  **ventana de un mes** hacia atrás desde la última (ids + fechas en la
  tabla `mediciones`). Nunca valores térmicos inventados.

```powershell
python -m colector_datos.db_sitios_marte indexar        # Gazetteer -> 1.133 'pendiente' (idempotente)
python -m colector_datos.db_sitios_marte enriquecer --max 50   # resumible; hilos 2-3 máx
python -m colector_datos.db_sitios_marte listar --n 15  # sitios 'listo' en formato de comparación
python -m colector_datos.db_sitios_marte estado
```

El flujo pensado para la app: `listar` ofrece opciones reales al usuario →
el sitio elegido (lat/lon/radio) se pasa a `obtener_datos_sitio("marte", ...)`,
que reproduce los números de la DB (verificado end-to-end en Jezero: mismo
tile, mismos valores). Detalles y sondeos: `NOTAS_NOCTURNAS.md` §17.

## Detalles de diseño (por qué está hecho así)

1. **Menos llamadas, más datos.** El GDS de Diviner devuelve los 9 canales en
   una única consulta (`channel="fffffffff"`): de ese solo CSV salen la
   temperatura (canales 3-9), el albedo (1-2), el día/noche (ángulo solar) y
   la estacionalidad (fecha). Lo mismo con LOLA: una descarga de puntos y
   pendiente/rugosidad/cráteres se calculan en Python, no en la red.
2. **Topografía por DTM cuando se puede, LOLA cuando hace falta**
   (`usar_dtm=True` por defecto): el tile Kaguya (~7 MB en S3 estático) da
   elevación/pendiente/rugosidad/cráteres sobre una malla de 19-30 m/px en
   segundos; el GDS LOLA (que el servidor fabrica a mano alzada, minutos) solo
   se consulta si el DTM no cubre la caja (típico en polos: huecos de sombra).
   En **Marte** es la única fuente puntual (no existe LOLA): DTMs de
   CTX/HiRISE a ~20 m/px con la misma receta y el mismo formato.
   La política exacta y sus mediciones están en `NOTAS_NOCTURNAS.md`.
3. **Paralelismo:** en consultas lunares, catálogo Treks + Diviner + STAC + DTM
   (o LOLA) se lanzan juntos en un `ThreadPoolExecutor(4)`; en Marte, Treks +
   STAC + análisis DTM en un pool de 3. El total es el de la llamada más
   lenta, no la suma.
4. **Tres cachés locales** (datos históricos: re-bajarlos da lo mismo):
   `cache_gds.py` (CSV de Diviner/LOLA), `cache_catalogo.py` (Treks/STAC) y
   los tiles DTM en `data/cache/dtm/`. Primera visita = red; siguientes =
   disco (medido: sitio nuevo 33 s frío → 4 s tibio).
5. **El catálogo de Treks se baja UNA vez** y todos los módulos lo filtran en
   memoria (`utilidades.capas_por_keyword`), sin repetir peticiones.
6. **Aislamiento de fallos:** si una fuente cae, la sección del diccionario
   correspondiente lleva `"error": ...` y el resto sigue funcionando; el DTM
   que no cubre degrada a LOLA sin romper nada.
7. **Cajas que cruzan el meridiano 0:** `utilidades.cajas_gds` las parte
   automáticamente en dos y SIEMPRE convierte la longitud al convenio 0-360
   que exige el GDS (sitios con longitud oeste fallaban antes).
8. **Python básico:** el flujo normal usa solo `pandas`; `numpy`+`rasterio`
   se importan SOLO dentro de la vía DTM, y su ausencia degrada a la vía
   LOLA con un mensaje claro. Cada función explica en su docstring qué hace,
   qué devuelve y de dónde sale cada número.

## Peculiaridades de los datos crudos (aprendidas a la dura)

- **LOLA (GDS `lolardr`):** cada fila trae 5 detectores (`D1..D5_*`), el radio
  de superficie está en **kilómetros**, los ecos perdidos son `-99`/`999`, y
  hay que NO confundir `SC_radius` (la nave, +50 km) con el radio del suelo.
  La longitud viene en el convenio 0-360 y se normaliza a ±180. Los radios
  descabellados (ruido del láser) se filtran con la desviación absoluta
  mediana (MAD) en `topografia.elevacion_lola`.
- **Diviner (GDS `divinerrdr`):** los 9 canales van como filas (`c`=1..9) y
  la columna `tb` del canal solar NO es temperatura (es la señal reflejada).
  La fecha viene como `01-Dec-2009` y se agrupa por mes del año (1..12) para
  el ciclo estacional lunar (~1 año terrestre). El ángulo cenital solar
  (`csunzen`) separa día (<90°) de noche (>=90°).
- **Polos:** el cálculo de pendiente/rugosidad se hace sobre una proyección
  plana local en metros (`utilidades.proyeccion_local`), porque en los polos
  1° de longitud son apenas unos metros y los cálculos en grados fallan.

## Registro de consultas

Cada llamada a `obtener_datos_sitio()` deja (o actualiza) su entrada en
**`colector_datos/data/registro_sitios.json`** — un JSON con una entrada por
sitio, cuya clave es `cuerpo@lat,lon±radio` (p.ej. `moon@-89.9,0.05±0.05`).
También se registran las consultas de TIERRA (`--cuerpo tierra`). Cada entrada
guarda:

- `fecha_consulta`: cuándo se pidió (repetir la consulta refresca la fecha).
- `resumen`: los números principales con nombre y unidad (elevación media,
  pendiente, temperatura, energía solar...), para hojear la base de sitios.
- `datos_completos`: el diccionario entero de esa consulta (sin la lista
  cruda de puntos LOLA, que queda resumida en `n_puntos`).

La ruta se cambia con la variable de entorno `NSAC_DATA_DIR` (por defecto
`colector_datos/data/`).

## Cuánto tarda cada consulta

- Treks, STAC, PDS Search y el lado Tierra: **segundos** (y de caché del disco
  tras la primera consulta del día: `cache_catalogo.py`).
- **Luna con `usar_dtm=True`:** primera visita ≈ **30-60 s** frío (el techo lo
  pone el GDS de Diviner; la topografía DTM añade solo 4-8 s). Sitio ya
  visitado: **~4 s** (medido).
- **Luna con `usar_dtm=False`:** los CSV crudos del GDS (LOLA/Diviner) tardan
  **varios minutos por consulta**, y el tiempo crece desproporcionadamente con
  el área pedida. Por eso `obtener_datos_sitio()` **recorta el radio a ±0.5°**
  (`constantes.RADIO_MAX_GRADOS`) y lo anota en `metadatos.nota_radio`: para
  más detalle, divide el sitio en sub-cajas.
- Si el servidor responde 502/503, la sesión de `nsac.http` reintenta hasta
  3 veces, lo que puede alargar una consulta lenta todavía más.

## Limitaciones conocidas

- El GDS puede tardar **minutos** por consulta; usa `usar_gds=False` para
  pruebas rápidas (catálogos y capas sin datos puntuales).
- El DTM de Kaguya cubre la caja SIEMPRE que el tile tenga >=50 % de píxeles
  válidos y >=90 % de la caja dentro del tile; en los **polos** falla por los
  huecos de sombra (medido: Malapert solo 2 % de píxeles) y el sistema cae
  automáticamente a la vía GDS LOLA.
- Un tile DTM cubre cajas de hasta ±0.5° si el tile es grande; cajas que
  abarquen VARIOS tiles necesitan mosaico (pendiente: hoy se usa 1 tile y la
  política de cobertura rechaza el resto — ver NOTAS_NOCTURNAS.md).
- En Marte no existen LOLA/Diviner: la temperatura puntual requiere descargar
  productos THEMIS/TES de PDS ODE (el módulo lo anota y da las capas Treks).
  La elevación puntual solo existe donde el STAC tiene DTM controlado
  (Jezero sí; Gale no): los demás sitios quedan con `nota_elevacion`.
- La detección de cráteres (malla o nube de puntos) es una **heurística de
  cribado**; para confirmar cráteres usa el mapa geológico USGS.
- `tipo_roca` es una clasificación por umbral de albedo (anortosita/basalto);
  crúzala con las capas de FeO/TiO₂ de Clementine para el informe final.
