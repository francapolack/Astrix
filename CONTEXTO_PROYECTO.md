# CONTEXTO_PROYECTO.md — Briefing autocontenido del proyecto NSAC

> Documento único para dar contexto a una IA externa (o a una persona nueva)
> sin tener que compartir el resto del repositorio. Fecha de última
> actualización: 15-nov-2026. Si los docs contradicen el código, gana el
> código (y se actualiza la nota — pauta del proyecto).

---

## 1. Qué es el proyecto

Toolkit Python para el **reto NASA Space Apps 2026** *"Permanent Moon Base
Locations and Mars"*: dado un sitio candidato de base en la **Luna** o en
**Marte** (lat, lon, radio), el colector descarga datos reales de la NASA/ESA
(sólo fuentes abiertas) y encuentra sus **análogos en la Tierra** — lugares
terrestres con condiciones físicas comparables (topografía, clima térmico,
albedo, iluminación).

- **Lenguaje**: todo el código, docstrings y comentarios en **español**
  (mantener esa pauta).
- **Python ≥ 3.10**, Windows (consola con acentos: `$env:PYTHONIOENCODING="utf-8"`).
- **Sin tests ni CI**: la verificación del proyecto es *ejecutar scripts*
  concretos y comparar sus salidas.

## 2. El producto real: una sola función

```python
from colector_datos import obtener_datos_sitio
d = obtener_datos_sitio(cuerpo='luna'|'marte'|'tierra',
                        lat=..., lon=..., radio=...)
```

Devuelve **UN diccionario** con secciones fijas:

```
metadatos / topografia / termico / superficie / iluminacion
```

con **las MISMAS claves en los tres cuerpos** para poder compararlos 1:1
(p. ej. `elevacion_m`, `pendiente`, `rugosidad`, `temperatura_superficial`,
`reflectancia_albedo`, `fraccion_diurna`...). Cada consulta deja una entrada
en `colector_datos/data/registro_sitios.json` (clave `cuerpo@lat,lon±radio`;
repetir una consulta ACTUALIZA su entrada; el `resumen` usa
`n_puntos_lola`, que con vía DTM cuenta PÍXELES — nombre histórico mantenido
por comparabilidad — y lleva `via_topografia`).

## 3. Arquitectura: 2 paquetes con roles distintos

```
nsac/             → CAPA DE ACCESO a fuentes HTTP (sólo hablar con APIs)
  http.py           sesión centralizada, reintentos, TLS
  sources/
    pds.py            NASA PDS GDS/ODE (Luna/Marte: Diviner, LOLA, THEMIS)
    usgs_stac.py      STAC de USGS Astrogeology (DTMs Kaguya/CTX/HiRISE)
    trek.py           catálogos de Solar System Treks (Moon/Mars Trek)
    earthdata.py      CMR (catálogo de la Tierra) + GIBS (teselas visor)
    copernicus.py     CDSE / Sentinel (cuenta sólo para descargas)
    csa.py, asf.py, jaxa.py, earthcode.py   (otras fuentes del reto)

colector_datos/   → EL PRODUCTO (los cálculos y la orquestación)
  api.py            obtener_datos_sitio() + registro de consultas
  constantes.py     radios de datum, presets de sitios, radios límites
  utilidades.py     matemática pura sin red (estadísticas, distancias)
  topografia.py     LOLA vía GDS (Luna, camino clásico)
  topografia_dtm.py DTM GeoTIFF vía rasterio (Luna: Kaguya; Marte: CTX/HiRISE)
  termico.py        Diviner (Luna): temperatura + reflectancia en 1 consulta
  superficie.py     albedo/rocas/minerales (Luna)
  iluminacion.py    horas de luz, energía solar, PSR (Luna/Marte)
  analogos_tierra.py  catálogos CMR/GIBS del "lado Tierra"
  topografia_tierra.py   → NUEVO (sesión 4): Copernicus DEM GLO-30/GLO-90
  termico_tierra.py      → NUEVO: NASA POWER (MERRA-2, TS)
  superficie_tierra.py   → NUEVO: Sentinel-2 L2A (Earth Search/Element84)
  iluminacion_tierra.py  → NUEVO: geometría solar local (0 llamadas)
  cache_gds.py           caché de CSVs GDS (data/cache_gds/)
  cache_catalogo.py      caché de catálogos Treks/STAC (data/cache/catalogos/)
  db_sitios_marte.py     DB local de sitios marcianos (Gazetteer + DTM)
  prueba_*.py / sonda_*.py / ejemplo_uso.py / prueba_funcion.py
```

Módulos que importan `numpy`/`rasterio` lo hacen **dentro de la función**
(vía DTM), de modo que el flujo básico funciona aunque falten esas deps
(degrada con mensaje a GDS LOLA, no rompe).

## 4. Estado actual (nov-2026): paridad Tierra COMPLETADA

La sesión 4 (rama `tierra-datos-crudos`, NOTAS §18-22) cerró la brecha:
`obtener_datos_sitio('tierra', ...)` ya devuelve **números crudos con las
mismas secciones/claves que Luna y Marte**, todo sin credenciales.

| Sección | Fuente Tierra | ¿Auth? | Tiempos medidos |
|---|---|---|---|
| Topografía | Copernicus DEM **GLO-30** (tile 1°×1° determinista, AWS público, ~30 m/px) | NO | frío 43-196 s (tile 37-42 MB, cacheado) / tibio **0.07 s** |
| Térmico | **NASA POWER** (MERRA-2 Earth Skin Temperature, 2 peticiones JSON) | NO | **3.2 s** (8 760 valores horarios) |
| Superficie | **Sentinel-2 L2A** via Earth Search (STAC de Element84, COG abiertos en AWS) | NO | frío ~42 s (5 bandas) / tibio **1-3 s** |
| Iluminación | **cálculo local** (geometría solar, 0 llamadas) | NO | <1 s |

La integración en `api.py` lanza los 3 módulos con datos en un pool de 3
hilos: consulta terrestre tibia ≈ **5 s** end-to-end.

**Tabla de paridad real** (`python -m colector_datos.prueba_tierra_comparacion --luna_completa`, NOTAS §19):

| Clave del resumen | TIERRA Atacama | LUNA Smythii | MARTE Jezero |
|---|---|---|---|
| elevacion_media_m | +1564 | -2325 | -2610 |
| pendiente_media_grados | 4.72 | 3.73 | 2.27 |
| rugosidad_media_m | 2.69 | 1.93 | 1.11 |
| temperatura_media_k | 292 | 230 | — |
| diferencia_dia_noche_k | 19.2 | 193 | — |
| variacion_estacional_k | 11.1 | 241 | — |
| reflectancia_media | 0.199 | 0.111 | — |
| energia_solar_media_wm2 | 573 | 799 | — |
| fraccion_diurna | 0.5 | 0.587 | — |
| n_puntos_lola (px) | 129 600 | 12 978 | 777 763 |
| via_topografia | glo30 | dtm_kaguya | dtm_mro |
| Tiempo de pared | 5.1 s tibio | 48.9 s frío | 0.6 s tibio |

Presets terrestres en `constantes.py`: `atacama` y `death_valley`.

## 5. La sub-rama GLO-90 (método rápido, ya fusionada)

El Copernicus DEM existe en dos resoluciones paralelas: **GLO-30** (30 m/px,
tiles de 37-42 MB, prefijo `COG_10`, bucket `copernicus-dem-30m`) y
**GLO-90** (90 m/px, tiles de 4-5 MB, prefijo `COG_30`, bucket
`copernicus-dem-90m`). Misma convención de nombres.

Comparativa medida (sub-rama `tierra-glo90-rapida`, fusionada con --ff-only,
NOTAS §20-bis) — primera visita SIN caché:

| Sitio | GLO-30 frío | GLO-90 frío | Δ elevación | Δ pendiente |
|---|---|---|---|---|
| Atacama ±0.05 | 43.6 s | **8.6 s** | 0.05 % | 4.72° → 3.90° |
| Death Valley ±0.1 | 61.5 s | **7.3 s** | 0.33 % | 19.0° → 15.8° |
| Haughton ±0.2 | 22.0 s | **2.2 s** | ~0 % | 5.79° → 4.87° |

Concepto clave: la **elevación media no depende de la resolución**, pero
**pendiente/rugosidad sí** (a 90 m el terreno corto se desenfoca — mismo
fenómeno que LOLA vs Kaguya en la Luna: dos fuentes del mismo parámetro no
son intercambiables si tienen resoluciones distintas, aunque el formato sea
idéntico). Veredicto: **GLO-30 sigue siendo el default** (fidelidad para
"¿se puede aterrizar?"); GLO-90 es la vía de **criba rápida** de muchos
sitios, activable con `topografia_tierra.analizar_sitio(..., resolucion='90m')`.

## 6. Complicaciones encontradas y cómo se resolvieron (lecciones reutilizables)

1. **Índice invisible de tiles**: el Copernicus DEM no necesita STAC ni
   búsqueda — la URL del tile se calcula en local con `floor(lat/lon)`.
   Pero la convención se descubrió sondeando: la **longitud lleva SIEMPRE
   3 dígitos** (`W070_00`, no `W70_00`); la latitud, 2. El bucket ES
   listable (GET S3 con `list-type=2`) — red de seguridad.
2. **Tiles de océano puro NO existen** (404): ESA no almacena tiles 100 % mar.
   El colector traduce ese 404 a mensaje semántico ("sitio en mar abierto").
3. **COG vs band-strided**: los tiles GLO-30 NO son COG (layout de bandas):
   una ventana remota de 360×360 px = 360 peticiones de rango ≈ 22 s. Por
   eso en la Tierra el default es DESCARGAR el tile y cachearlo (tibio
   0.07 s; el modo `remoto` sigue disponible). Los COG de Sentinel-2 sí
   permiten lectura remota de ventana (~13 s/banda frío). Moraleja: medir
   el layout interno de cada dataset antes de decidir descargar-cachear
   o leer-ventana.
4. **Sentinel-2 viene en UTM** (EPSG:32719, metros): hay que transformar la
   caja de EPSG:4326 con `rasterio.warp.transform` antes del window read —
   pasar lon/lat directo da ventanas 0×0. (En la Tierra PROJ funciona;
   en Luna/Marte hay CRS IAU con fórmulas manuales.)
5. **Dentro de UN producto S2 hay 2 resoluciones**: la SCL (clasificación,
   máscara de nubes/agua) va a 20 m y las bandas a 10 m → sobremuestrear la
   máscara 2×2 con vecino más próximo (no interpolar clases).
6. **`rasterio.warp` no viene con `import rasterio`**: importar explícito.
7. **Bug corregido en `nsac/sources/earthdata.py`**: CMR devuelve
   `granule_size` como float ("6.444…") y `int()` casca → ahora `float()`.
8. **El HEAD MIENTE**: MOD11A2 respondía HEAD 200 pero GET real **401**
   (rutas `lp-prod-protected`); Landsat redirige (302) al login de EROS.
   Regla: verificar acceso con **GET de rango** (`bytes=0-2047`), nunca con
   HEAD. (Así se descartaron Landsat/MODIS para la vía sin-credenciales.)
9. **Rugosidad falsa a 90 m/px**: una celda de 100 m contiene 1 píxel →
   std = 0 ("terreno liso" falso). Fix: celda mínima de 2 px por lado, con
   `tamano_celda_m` reportado.
10. **Varianza de reanálisis**: la media anual de POWER varió (294.171 vs
    291.771 K, n=8760 igual) porque es un modelo vivo que refresca series.
    No comparar térmicas de POWER con más de 1 decimal entre corridas.

Gotchas históricos que siguen vigentes (Luna/Marte):
- Convenciones de bbox NO homogéneas: CMR/STAC `(oeste,sur,este,norte)`;
  ODE/GDS `(minlat,maxlat,oeste,este)`; ASF `(sur,oeste,norte,este)`.
- El GDS de PDS trabaja en longitudes 0-360 y es LENTO (minutos) y frágil:
  `cajas_gds` ya convierte/parte; radio recortado a ±0.5°
  (`constantes.RADIO_MAX_GRADOS`); llamadas en paralelo.
- CRS lunares/marcianas: PROJ no las transforma (Kaguya `IAU_2015:30100`
  en grados; tiles CTX/HiRISE `IAU_2015:49910` en METROS con fórmula manual
  R=3396190; tiles polares `stere` marcianos: error claro, sin dato).
- Política DTM (en `api.py`, no cambiar a la ligera): Luna exige ≥50 %
  píxeles válidos Y ≥90 % cobertura (cae a GDS LOLA si falla); Marte solo
  ≥50 % (no hay respaldo). Sufijos DEM aceptados: `-dem.tif` (Kaguya) y
  `_dtm.tif` (CTX/HiRISE).
- Si una fuente no da el dato → `nota` honesta (como Marte con THEMIS).
  **NUNCA inventar números.**

## 7. Cachés y datos locales (`data/` gitignored, sin caducidad)

- `data/cache_gds/` — CSVs Diviner/LOLA (GDS).
- `data/cache/catalogos/` — catálogos Treks/STAC/Earth Search (JSON con fecha).
- `data/cache/dtm/` — tiles DEM descargados (Kaguya/CTX/GLO-30/GLO-90).
- `data/cache/s2/` — ventanas de bandas Sentinel-2 (`.npz`).
- `data/db/sitios_marte.db` — DB de sitios marcianos.
- `data/registro_sitios.json` — registro de consultas.
- Ruta raíz configurable con `NSAC_DATA_DIR`. Sitio tibio ≈ 4-5 s vs
  33-95 s frío.

## 8. Credenciales

**Nada de lo anterior requiere cuenta.** Las credenciales (`.env.example`
→ `.env`) son SOLO para descargas opcionales:
- `EARTHDATA_USERNAME/PASSWORD`: Earthdata Login — permitiría la vía
  MEJORADA del térmico terrestre: MOD11A2 (MODIS LST real de 1 km en vez
  del reanálisis POWER de ~50 km). Granules verificados tras login (401
  sin auth). Pendiente de implementar (leer HDF4 con rasterio).
- CDSE (descargas Sentinel) y JAXA G-Portal: otras cuentas del proyecto.
- CSA usa un certificado Entrust retirado: `nsac.http` reintenta sin
  verificar TLS solo para esos hosts (`NSAC_INSECURE_HOSTS`).

## 9. Git (estado)

- Ramas locales: `master` (sólo remota, atrás) ← `dtm-rasterio` (optimización
  GDS + DTM + Marte + DB) ← **`tierra-datos-crudos`** (sesión 4, ACTUAL,
  9 commits) ← con la sub-rama **`tierra-glo90-rapida`** fusionada (--ff-only).
- Push ha dado 403 con la credencial de este dispositivo (NOTAS §11):
  Axel empuja desde el suyo.
- Lección repetida de la bitácora: un fix no está hecho hasta que está
  **comiteado**.

## 10. Comandos de verificación (NO hay tests/CI: se ejecutan scripts)

```powershell
python -m venv .venv; .\.venv\activate ; pip install -r requirements.txt
$env:PYTHONIOENCODING="utf-8"     # imprescindible en consola Windows

python -m nsac.cli doctor                        # 14 fuentes en vivo, sin credenciales
python -m colector_datos.ejemplo_uso --rapido    # fumo del colector (sin GDS, segs)
python -m colector_datos.prueba_funcion --sitio malapert   # informe completo (GDS: minutos)
python -m colector_datos.prueba_dtm --lat 41.2 --lon -23.7 --radio 0.05   # A/B DTM vs LOLA
python -m colector_datos.db_sitios_marte estado  # DB de sitios marcianos

# NUEVO (sesión 4, Tierra):
python -m colector_datos.prueba_tierra_dtm       # piloto topografía GLO-30
python -m colector_datos.prueba_tierra_glo90     # comparativa GLO-30 vs GLO-90
python -m colector_datos.prueba_tierra_comparacion --luna_completa
                                                 # resumen tierra/luna/marte lado a lado
```

Los módulos se ejecutan como `python -m colector_datos.<modulo>` **desde la
raíz** (donde está `pyproject.toml`), no desde dentro del paquete.

## 11. Pendiente (todo opcional, extensiones no deudas)

1. **MOD11A2 con Earthdata** (término "medido" de 1 km vs reanálisis ~50 km)
   — la mejora de fidelidad más grande que queda en la Tierra.
2. **Aerosol/polvoreda** terrestre (análogo del polvo marciano): Sentinel-5P
   (abierto, NetCDF) o MODIS aerosol (Earthdata).
3. **SMAP humedad de suelo** (análogos de hielo/criosfera) — Earthdata.
4. **Mosaico multi-tile GLO-30** para cajas que pisan 2 tiles en el
   antimeridiano (hoy se pierde un lado y se reporta `cobertura < 1`).
5. **Push de las ramas** al remoto (bloqueo 403 de este dispositivo).
6. Perillas ya disponibles para experimentar: `resolucion='30m'|'90m'`
   (fidelidad vs criba), `modo_tile='descargar'|'remoto'`, radio ≤ ±0.5°,
   y en S2 la escena elegida (hoy: la más reciente con <50 % nubes).

## 12. Referencias internas

- `colector_datos/NOTAS_NOCTURNAS.md` — bitácora completa por sesión
  (§18-22 = sesión 4, Tierra). Fuente de verdad de mediciones.
- `AGENTS.md` — guía compacta de agentes (comandos + gotchas).
- `colector_datos/README.md` — mapa parámetro→módulo→fuente.
- Sesiones de prueba reales usadas como sitios: Malapert/Peary/Shackleton
  (polos lunares), Smythii (mar lunar), Jezero/Gale (Marte), Atacama y
  Death Valley (análogos terrestres).
