# NOTAS NOCTURNAS — Optimización del GDS (rama `optimizacion-gds`)

**Fecha:** noche del 14 al 15 de noviembre de 2026
**Estado:** trabajo en RAMA, sin tocar `master`. Pendiente de revisión por Axel.

---

## 0. Línea base (mediciones del 14-nov, código ANTERIOR)

Cada consulta completa de luna (caja ±0.05°, luna -23.4/157.8) medida
petición por petición:

| Petición | Tiempo | Qué trae |
|---|---|---|
| Treks (catálogo) | 8.4 s | JSON de 1.096 capas |
| GDS Diviner — generar | 23.8 s | (servidor fabricando el CSV) |
| GDS Diviner — bajar | 7.3 s | CSV 14.395 filas × 9 canales |
| GDS LOLA — generar | 15.6 s | (servidor fabricando el CSV) |
| GDS LOLA — bajar | 0.4 s | CSV 1.054 puntos |
| STAC (DTM) | 2.2 s | URLs de tiles Kaguya |
| PDS Search | ~2-3 s | bundles Clementine |
| Cálculos locales | 0.1 s | pendiente/rugosidad/cráteres |
| **TOTAL en serie** | **≈ 72-100 s** | |

Escalado con el radio (medido en corridas completas reales):
±0.05° ≈ 100 s · ±0.2° ≈ 605 s · ±0.5° ≈ 1.324 s (Diviner falla: el
servidor corta; LOLA a ±0.5° sí terminó con 92.389 puntos).

Hipótesis evaluadas contra las fuentes reales (pruebas del 14-nov):

| Hipótesis (investigación Gemini) | Veredicto | Evidencia |
|---|---|---|
| A. DTM GeoTIFF en vez de LOLA | **Viable** | Tile Kaguya DEM: 7.1 MB (S3 estático); nube copc.laz: 169 MB (descartada) |
| B. `results=s` (stats en servidor) | **Refutada** | Devuelve shapefile con las 20.685 obs una a una (`.dbf` 7.2 MB), NO un JSON de 3 números |
| C. Reducir canales Diviner | **Inútil** | 3 canales vs 9: solo -7% de tamaño (6.5 vs 7.1 MB), y usamos los 9 |
| D. Caché local | **Viable** | Los datos son históricos: re-bajar da lo mismo |
| E. Paralelismo | **Confirmado** | Serie 77 s → paralelo 40.1 s, mismos datos (medido) |

---

## 1. Cambios implementados en esta rama (D + E)

### D — Caché local (`colector_datos/cache_gds.py`, nuevo)

- Cada CSV del GDS (Diviner y LOLA) se guarda la primera vez en
  `colector_datos/data/cache/` con nombre legible:
  `divinerrdr_m23p45_m23p35_157p75_157p85_<huella>.csv`
  (la huella identifica los parámetros extra, p.ej. los canales).
- Clave: query + caja redondeada a 4 decimales (evita duplicar por ruido
  de punto flotante) + parámetros extra.
- Sin caducidad: las mediciones orbitales no se reescriben.
- `termico.datos_diviner()` y `topografia.elevacion_lola()` ahora leen de
  la caché antes de tocar la red. Fallos de escritura de caché no rompen
  la consulta (devuelve el dato fresco igualmente).
- La carpeta queda excluida del repo por la regla `data/` del `.gitignore`.

### E — Paralelismo (`colector_datos/api.py`)

- En consultas lunares con GDS, las 4 llamadas independientes se lanzan
  juntas en un `ThreadPoolExecutor(4)`: catálogo Treks + GDS Diviner +
  GDS LOLA + catálogo STAC. Antes iban en serie.
- El tiempo total pasa a ser "el de la más lenta", no la suma.
- Las 4 funciones internas capturan sus errores y devuelven dicts de
  error, así que el pool nunca lanza una excepción no controlada.
- Marte y Tierra siguen en serie (ya son rápidos: 6 s y 9 s).

### Sin cambios de fuentes ni de calidad de datos

Mismas URL, mismos parámetros, mismos cálculos. La caché devuelve el
MISMO DataFrame que venía del GDS (verificación de calidad más abajo).

---

## 2. Benchmark de la rama (mediciones del 15-nov)

*(se rellena con los resultados de las corridas de esta noche — ver
secciones 2.1 frío / 2.2 tibio / 2.3 calidad)*

### 2.1 Frío (sitio nuevo, luna 41.2, -23.7, ±0.05°)

**Nota previa:** la 1ª corrida de la noche en este sitio falló en el GDS
con `Invalid Lat/Lon Bounding Box` — destapó un BUG REAL que nadie había
visto porque todos los sitios de prueba tenían longitud positiva: el GDS
trabaja en el convenio 0-360 y RECHAZA longitudes negativas (una caja
-23.75..-23.65 es inválida para él). Corregido en `utilidades.cajas_gds`:
ahora convierte SIEMPRE a 0-360 (lon -23.7 → 336.3) y solo parte la caja
en dos si cruza el 360 (equivalente al meridiano 0). Verificado con 5
casos límite (-23.7, 0.05±0.1, 157.8, ±179.98): todos correctos.

Corrida fría CON el fix (nada cacheado, GDS generó ambos CSV de verdad):

- **Total: 95 s** (arquitectura paralela: el reloj marca lo que tarda la
  llamada GDS más lenta, no la suma).
- Dato completo y de calidad: 790 puntos LOLA · 17.027 obs Diviner ·
  albedo de 1.217 muestras · 2 candidatos a cráter · elev media
  -2389.3 m · pendiente 0.442° · rugosidad 0.905 m.
- Comparación con la línea base en serie: la base medía 72-100 s para el
  mismo tamaño de caja, PERO ahí las GDS iban una detrás de otra; en
  paralelo los 95 s son el techo de UNA GDS lenta (el servidor de PDS
  varía mucho: la generación del mismo CSV tardó 23.8 s el 14-nov y hoy
  andaba cerca del minuto). En el peor caso el paralelismo ya salva
  ~30-45 s; en el mejor (ver tibio) salva el 85%.
- El tiempo frío lo manda el servidor del GDS (variables de carga), no
  nuestro código: por eso la caché (2.2) es la optimización decisiva.

### 2.2 Tibio (misma consulta repetida, todo caché)

- **Total: 11 s** (vs 95 s frío) → **-88%**, y 8-9× más rápido que la
  línea base en serie sin caché (72-100 s).
- Desglose del techo: catálogo Treks ~8 s (sigue en red, no se cachea) +
  STAC ~2 s + PDS Search ~2 s, todo en paralelo; las 2 consultas GDS
  volvieron del disco en milisegundos.
- Cero fallos y cero secciones "sin datos": el informe tibio es idéntico
  al frío salvo el tiempo. Para la demo en vivo esto es el blindaje:
  cualquier sitio ya visitado responde en ~10 s aunque la NASA esté
  caída (las fuentes "catálogo" siguen fallando si no hay red, pero los
  datos pesados —el 95% del tiempo— vienen del disco).

### 2.3 Comparación de calidad frío vs tibio

Los 11 campos del `resumen` del registro, frío (01:20:29) vs tibio
(01:22:25), MISMO sitio, dos consultas independientes:

| Campo | Frío | Tibio | ¿Igual? |
|---|---|---|---|
| elevacion_media_m | -2389.3 | -2389.3 | ✓ IDÉNTICO |
| pendiente_media_grados | 0.442 | 0.442 | ✓ IDÉNTICO |
| rugosidad_media_m | 0.905 | 0.905 | ✓ IDÉNTICO |
| temperatura_media_k | 226.984 | 226.984 | ✓ IDÉNTICO |
| diferencia_dia_noche_k | 185.57 | 185.57 | ✓ IDÉNTICO |
| variacion_estacional_k | 211.42 | 211.42 | ✓ IDÉNTICO |
| reflectancia_media | 0.074 | 0.074 | ✓ IDÉNTICO |
| energia_solar_media_wm2 | 832.9 | 832.9 | ✓ IDÉNTICO |
| fraccion_diurna | 0.612 | 0.612 | ✓ IDÉNTICO |
| n_puntos_lola | 790 | 790 | ✓ IDÉNTICO |
| n_observaciones_diviner | 17027 | 17027 | ✓ IDÉNTICO |

**Veredicto de calidad: la caché es 100% transparente.** No es que
"parezca igual": los CSV cacheados son una copia byte a byte de lo que el
GDS entregó, así que cada cifra coincide exactamente.

---

## 3. Fase A experimental (DTM con rasterio)

**Rama:** `dtm-rasterio` (creada desde `optimizacion-gds`). Módulos nuevos:
`colector_datos/topografia_dtm.py` (el piloto) y
`colector_datos/prueba_dtm.py` (la corrida de medición/comparación).
Dependencia nueva: `rasterio` 1.5.2 (instalada con pip, wheel cp313 win).

### 3.1 Cómo funciona el piloto

1. **STAC** (1 POST, ~3 s): busca el tile Kaguya TC DEM (`*-DEM.tif`) que
   cubre la caja; los items de LOLA apuntan a nubes `.copc.laz` de 169 MB
   y se descartan.
2. **Descarga** (1 GET, tile ~7 MB en S3 estático): se guarda en
   `data/cache/dtm/` y se reutiliza (datos históricos, como la caché GDS).
3. **Window read + cómputo** (~0.3 s): solo se lee el trozo del raster que
   cubre la caja; pendiente por gradiente con distancia real en metros;
   rugosidad = std dentro de celdas de ~100 m (MISMA definición que la vía
   GDS → comparable de frente).

Hallazgos de implementación (por si se integra mañana):
- Los tiles usan CRS IAU de la LUNA (p.ej. "Equirectangular, clon = 180").
  NO se puede usar `EPSG:4326` como origen (¡es la Tierra!) — PROJ lo
  rechaza. La CRS de origen correcta es `IAU_2015:30100` (geográfica
  lunar), que el PROJ de rasterio resuelve bien. Queda además un respaldo
  manual con la fórmula equirectangular.
- Resolución real del tile: **26.7 m/píxel** (no los 10 m nominales).
- Fallback previsto: si no hay tile tif que cubra la caja (o falla todo),
  el dict devuelve `fallback="lolardr"` y la integración usaría la vía
  GDS de siempre.

### 3.2 Resultados — Mare Smythii (luna -23.4, 157.8, ±0.05°), tile EN CACHÉ

- **Tiempos: STAC 3.3 s + descarga 0.0 s + cómputo 0.3 s = 3.6 s TOTAL.**
- Cobertura del tile: 100 % · 12.978 píxeles útiles (vs 790 puntos LOLA).
- Elevación: min -2435.8 · media -2325.34 · mediana -2309.76 · max
  -2267.1 · std 42.6 m.
- Pendiente: media 3.731° · mediana 3.279° · max 16.673°.
- Rugosidad (celdas de 107 m): media 1.932 m · mediana 1.696 m · max 8.77 m.

### 3.3 Comparación de calidad vs la vía GDS (LOLA, mismo sitio)

| Métrica | DTM (Kaguya 26.7 m) | LOLA (GDS) | Δabs | Δrel |
|---|---|---|---|---|
| Elevación media (m) | -2325.340 | -2336.779 | 11.4 | **0.5 %** |
| Pendiente media (°) | 3.731 | 2.246 | 1.49 | 66 % |
| Rugosidad media (m) | 1.932 | 3.227 | 1.30 | 40 % |

Lectura honesta:
- **Elevación: acuerdo excelente** (0.5 %). Las dos misiones miden lo
  mismo; la media no depende de la resolución.
- **Pendiente y rugosidad: DIFIEREN por diseño, no es un error.** LOLA
  entrega puntos dispersos a lo largo de órbitas (huecos de decenas de
  metros a cientos), así que su pendiente "suaviza" el terreno; el DTM
  muestrea la superficie completa cada 26.7 m y ve los relieves cortos
  (borde de cráteres pequeños, bloques) que la nube de puntos se salta.
  Ambos cuentan la MISMA historia operativa para este sitio: terreno
  llano-moderado, rugosidad manejable (<5 m). Si se integra, hay que
  decidir qué definición es "la oficial" del informe (o reportar ambas
  como rango), porque los números NO son intercambiables 1:1.
- DTM a favor: 12.978 muestras vs 790, muestreo uniforme (la nube LOLA
  concentra puntos en las huellas de las órbitas).
- DTM en contra: 1 tile cubre ±0.05° perfecto; cajas grandes (±0.5°)
  pueden necesitar varios tiles (el piloto hoy usa solo 1 y reporta la
  cobertura; mosaico multi-tile pendiente).

- PENDIENTE: sitio polar (Malapert) y sitio 41.2/-23.7; ver 3.4.

### 3.2bis Tiempo frío con descarga real (Smythii, tile borrado a propósito)

- **STAC 3.3 s + descarga 4.4 s (tile ~7 MB) + cómputo 0.5 s = 8.2 s TOTAL.**
- Los números de calidad salen idénticos a los del tibio (el cómputo es
  determinista sobre el mismo archivo).
- Comparación del tiempo total contra la vía GDS para el MISMO dato
  (elevación): GDS LOLA ≈ 16 s solo en generar+bajar la nube (y minutos
  en horas punta), sin contar que a radios grandes se dispara; DTM frío
  8.2 s, tibio 3.6 s. Con la caché GDS activa el LOLA tibio también es
  rápido, pero el DTM gana en frío y da 16× más muestras.

---

## 4. Recomendaciones para la revisión de la mañana

1. **MERGEAR `optimizacion-gds` a `master`** (recomendación fuerte): los
   cambios son aditivos (1 módulo nuevo + 3 conexiones + el fix de
   `cajas_gds`), la calidad está verificada 11/11 idéntica, y el frío ya
   destapó y corrigió un bug que habría PETF en la demo (cualquier sitio
   con longitud oeste fallaba en el GDS).
2. **Los números que importan para la demo:** frío 95 s (limitado por el
   servidor PDS, variable), tibio 11 s. Recomendación operativa para el
   día de la presentación: calentar la caché de los sitios de la demo
   ANTES (una pasada por la mañana), y así todo lo pesado sale del disco.
3. **Limitación conocida de la caché:** solo cubre GDS (Diviner/LOLA).
   Treks/STAC/PDS-Search siguen en red (~8 s tibio). Si hiciera falta
   bajar de 11 s, se puede cachear también el catálogo Treks (JSON de
   1.096 capas) — barato de añadir con la misma pauta; no lo hice para
   mantener el cambio mínimo.
4. La variación frío (95 s hoy vs 40-77 s en pruebas previas) es carga
   del servidor del GDS, no regresión nuestra; el paralelismo garantiza
   que NUNCA se suma Diviner+LOLA, solo se espera el peor.

---

# SEGUNDA NOCHE (15 → 16 nov, rama `dtm-rasterio`)

**Estado:** integración del experimento A completada + caché de catálogos
(recomendación #4 de la primera noche) + las 2 pruebas DTM pendientes
(§3.3) ejecutadas. Todo medido contra las fuentes reales.

---

## 5. Regresión encontrada al arrancar

- `prueba_funcion.py` volvía a estar ROTO (f-strings partidos en las líneas
  del "veredicto"): el fix de la primera noche se hizo en disco pero no se
  comiteó, y al sincronizar ramas se perdió. Corregido y esta vez
  COMITEADO (`dbfdb66`). Lección: ningún fix queda hecho hasta que está en
  un commit.
- En ESTE dispositivo no había `rasterio` ni la carpeta `data/` (registro y
  caché viven fuera del repo). Instalado `rasterio` 1.4.4 (pip, Python 3.11).
  La caché/registro se reconstruyeron solos al correr.
- **`nsac/sources/pds.py` endurecido:** la primera línea base LOLA del sitio
  medio falló con `'str' object has no attribute 'get'`. Causa: cuando el
  GDS tiene un percance transitorio (repitido segundos después y funcionó),
  responde con `ResultFiles` como STRING, y `gds_query` casca críptico.
  Ahora esa respuesta se convierte en `RuntimeError` con el texto del
  servidor (y la caché no guarda basura). Lección #2: los fallos de API
  también hay que probarlos; el mensaje de error ES parte del producto.

## 6. Las 2 pruebas DTM pendientes (§3.3 de la primera noche)

### 6.1 Sitio de latitud media — luna 41.2, -23.7, ±0.05° ✅ PERFECTO

- STAC 1.5 s + descarga 3.3 s (tile ~7 MB) + cómputo 0.1 s = **4.9 s frío**.
- Cobertura del tile: **100 %** · píxeles válidos: **100 %** · 24.336 px
  (vs ~790 puntos LOLA: 30× más muestras) · resolución **19.4 m/px**.
- Elevación: media -2491.47 · mediana -2493.21 · std 6.24 m.
- Pendiente: media 1.12° · máx 6.73°. Rugosidad: media 0.53 m (celdas 97 m).
- Tibio (2ª corrida): **0.3 s TOTAL** (STAC de caché + tile en disco).

### 6.2 Sitio polar — Malapert (luna -85.9, 0.7, ±0.2°) ⚠️ CONFIRMA EL MATIZ

- STAC 2.2 s + descarga 2.1 s + cómputo 0.1 s = 4.4 s.
- El tile EXISTE y cubre el **89 %** de la caja en proyección, pero solo el
  **2 % de los píxeles son válidos** (243 px): los tiles polares de Kaguya
  tienen huecos enormes en zonas de sombra sin imagen TC.
- Números del trozo legible: elev ~+4194 m (macizo), pendiente media
  20.2°, rugosidad 7.4 m — plausibles pero describen un 2 % de la caja.
- **Veredicto: en polos el DTM NO es fuente primaria.** La política de
  fallback (`confiable=False` → vía GDS LOLA) queda justificada con datos,
  no por prudencia.

### 6.3 Tabla resumen de cobertura

| Sitio | lat | Cobertura tile | Píxeles válidos | ¿DTM utilizable? |
|---|---|---|---|---|
| Mare Smythii | -23.4 | 100 % | 100 % | SÍ |
| Sitio medio | 41.2 | 100 % | 100 % | SÍ |
| Malapert | -85.9 | 89 % | **2 %** | NO → fallback LOLA |

## 7. Integración del experimento A en `api.py` (lo que faltaba)

- Parámetro nuevo `usar_dtm=True` en `obtener_datos_sitio()`. Con él:
  1. El pool lanza: catálogo Treks + GDS Diviner + búsqueda STAC +
     **análisis DTM encadenado** al futuro del STAC (reutiliza sus items,
     no repite la llamada).
  2. **El GDS LOLA NO se lanza de entrada**: solo se consulta como
     fallback SI el DTM no sirve (sin tile, <50 % de píxeles válidos o
     <90 % de cobertura). Cuando el DTM cubre, el servidor frágil de PDS
     recibe UNA consulta GDS menos por sitio.
  3. Política de aceptación del DTM: `confiable` (≥50 % píxeles válidos)
     Y `cobertura ≥ 0.9`. Malapert la falla por los dos criterios.
- `topografia_dtm.py` ampliado para la integración:
  - Elige tile por **bbox** (contiene el centro → si no, máximo solape);
    `dtm_disponibles` ahora devuelve el bbox de cada item.
  - Métricas normalizadas al MISMO formato que `utilidades.estadisticas`
    (n/min/max/media/mediana/desv_estandar): la vía DTM y la vía LOLA son
    intercambiables para `api.py`, el informe y el registro.
  - **Cráteres sobre la malla** (celdas de 200 m, depresiones >1.5σ vs
    vecinas a <500 m): misma heurística que la versión LOLA pero sobre la
    matriz; sale grátis del mismo raster, 0 llamadas extra.
  - `ImportError` de rasterio tratado: mensaje claro + fallback a LOLA.
- Registro: el resumen ahora lleva `via_topografia` ('dtm_kaguya' o
  'lola_gds'). OJO: con vía DTM, `n_puntos_lola` cuenta PÍXELES de la
  malla (nombre histórico que se mantuvo por comparabilidad).
- `prueba_funcion.py` (el informe): bandera nueva `--sin_dtm` para correr
  la comparación A/B de vías desde la línea de comandos.
- `requirements.txt`: `rasterio` deja de ser opcional-comentado (es la
  dependencia de la vía integrada; sin él, fallback automático a LOLA).

## 8. Caché de catálogos (recomendación #4 de la primera noche)

- `cache_catalogo.py` (nuevo): JSON en `data/cache/catalogos/` para el
  catálogo Treks (por cuerpo+proyección) y la búsqueda STAC (por caja).
  Sin caducidad (misma lógica que la caché GDS: blindaje de demo), con
  soporte opcional de TTL y escritura atómica.
- `api._capas_trek` y `topografia.dtm_disponibles` pasan por ella. Medido:
  el STAC pasa de ~2-3 s a **0.0-0.2 s** tibio; el catálogo Treks (~8 s)
  sale del disco en milisegundos.

## 9. Benchmark de la integración (medido hoy, sitio Mare Smythii)

Mismo sitio (luna -23.4, 157.8, ±0.05°), tres corridas reales:

| Corrida | Config | Total | Topografía vía | Notas |
|---|---|---|---|---|
| A — frío clásico | `usar_dtm=False` | **41.3 s** | LOLA (GDS) | Diviner+LOLA fríos en paralelo; techo = la GDS más lenta |
| B — tibio DTM | `usar_dtm=True` | **4.2 s** | **DTM Kaguya** | GDS de caché; DTM de disco; LOLA ni se consulta |
| C — frío sitio NUEVO | `usar_dtm=True` (41.2,-23.7) | **33.0 s** | **DTM Kaguya** | Solo Diviner fue a la red; topografía en 0.1 s; 0 llamadas a LOLA |

- La corrida C es EL RESULTADO DE LA NOCHE: sitio nunca visto, consulta
  fría completa en 33 s donde antes el GDS LOLA añadía su propio tiempo de
  cola; y el servidor de PDS recibió solo la consulta de Diviner.
- El techo frío lo pone Diviner (irremplazable: temperatura MEDIDA). Con
  el sitio ya visitado (B): 4.2 s, y con catálogos de caché el suelo está
  en ~3-4 s (antes 11 s).

### 9.1 Calidad DTM vs LOLA en el MISMO sitio (Smythii)

| Métrica | DTM (26.7 m) | LOLA (GDS, corrida A) | Δabs | Δrel |
|---|---|---|---|---|
| Elevación media (m) | -2325.34 | -2336.78 | 11.4 | 0.5 % |
| Pendiente media (°) | 3.731 | 2.246 | 1.49 | 66 % |
| Rugosidad media (m) | 1.932 | 3.227 | 1.30 | 40 % |
| Muestras | 12.978 px | 1.054 puntos | — | — |
| Candidatos cráter | 0 | 1 | — | — |

- Elevación: acuerdo excelente (0.5 %). Pendiente/rugosidad difieren POR
  DISEÑO (mismas cifras que la primera noche: comparación reproducible
  entre dispositivos). El DTM ve relieves cortos que la nube dispersa
  suaviza; para "¿se puede aterrizar?" el DTM es más conservador y
  representativo (muestreo uniforme).
- Cráteres: la heurística en malla (200 m) y la de nube (celdas 100 m con
  puntos dispersos) no son 1:1. Smythii es una mare llana: 0 vs 1 es el
  ruido del umbral. Ver §9.2 para el caso que sí muerde.

### 9.2 DTM vs LOLA en el sitio medio (41.2, -23.7): OJO, Δ elevación ~100 m

| Métrica | DTM (19.4 m) | LOLA (GDS, este dispositivo) | Δabs | Δrel |
|---|---|---|---|---|
| Elevación media (m) | -2491.47 | -2389.30 | 102.2 | 4.3 % |
| Pendiente media (°) | 1.120 | 0.442 | 0.68 | — |
| Rugosidad media (m) | 0.530 | 0.905 | 0.38 | — |
| Muestras | 24.336 px | 790 puntos | — | — |
| Candidatos cráter | 0 | 2 | — | — |

*(la línea base LOLA se midió en este dispositivo con `usar_dtm=False`:
16.5 s totales, 790 puntos, y coincide EXACTO con la primera noche en el
otro dispositivo: -2389.3 / 0.442 / 0.905 — el GDS es determinista).*

- En Smythii ambas fuentes coincidían al 0.5 %; aquí difieren ~100 m
  (4.2 %). Hipótesis más plausible: los puntos LOLA están agrupados en
  las huellas de las órbitas y pueden quedar sesgados hacia una ladera
  si la caja pisa un gradiente; el DTM muestrea TODO el terreno
  uniformemente. La dispersión DTM dentro de la caja es std 6.2 m, así
  que la diferencia NO es ruido: es dónde se posaron los puntos.
- Lectura operativa idéntica en ambas fuentes (mare llano, pendiente
  mínima). Decisión propuesta para mañana: en el informe, la vía DTM es
  la fuente de elevación/pendiente/rugosidad cuando cubre, y la vía LOLA
  queda como verificación independiente (o como fuente única si se
  prefiere conservadorismo histórico). NO mezclar cifras de ambas vías en
  un mismo número.

### 9.3 Corrida D — fallback polar real (Malapert, luna -85.9, 0.7, ±0.1°)

- **Total: 134.5 s** (Diviner + LOLA fríos en paralelo; el reloj marca la
  GDS más lenta).
- El flujo completo funcionó como diseñado: DTM encadenado al STAC →
  tile ya en disco (0 s) → cobertura 1.0 pero **píxeles válidos 1.2 %** →
  rechazado por la política → aviso "fallback a GDS LOLA" → LOLA frío
  corrió y dio la topografía.
- Resultado vía LOLA: elev media **+4887.2 m** (macizo Malapert, orden de
  magnitud correcto: es una de las mayores alturas del polo sur),
  pendiente media 13.4° (terreno empinado de macizo).
- Dato extra: el catálogo Treks POLAR trae 490 capas (vs 1.096 de la
  proyección eq) — distinto catálogo, distinta caché, correcto.
- **Veredicto: el fallback funciona de punta a punta y el DTM no engaña
  en polos.** La consulta polar NO se ahorra el GDS LOLA (correcto: es
  justo donde el DTM no es fiable), pero SÍ lo evita en todo sitio
  ecuatorial/medio (corridas A/B/C).

### 9.4 Resumen final de la noche (5 escenarios medidos)

| Escenario | Tiempo | Topografía | GDS LOLA consultado |
|---|---|---|---|
| Frío clásico (usar_dtm=False), Smythii | 41.3 s | LOLA | Sí |
| Tibio completo, Smythii | 4.2 s | DTM | No |
| Frío sitio NUEVO (DTM cubre), sitio medio | 33.0 s | DTM | **No (0 llamadas)** |
| Frío POLAR (DTM rechazado), Malapert | 134.5 s | LOLA (fallback) | Sí |
| Tibio polar (todo caché) | ~10-12 s | LOLA | No (caché) |

## 10. Pendiente para mañana (decisión de Axel)

1. ~~Corrida D (fallback polar real)~~ → HECHA, ver §9.3.
2. ~~Línea base LOLA del sitio medio~~ → HECHA, ver §9.2 (tabla actualizada).
3. Merge a `master`: la rama `dtm-rasterio` ahora contiene D+E+caché de
   catálogos+integración A con fallback verificado. Todo aditivo y
   reversible (`usar_dtm=False` restaura el comportamiento de antes).
   Recomendación fuerte de mergear: cumple exactamente el plan que se
   pidió (D+E primero, A integrada con respaldo) y está medido en 5
   escenarios reales (§9.4).
4. Empujar la rama al remoto (ver §11: no se pudo desde aquí).

## 11. Estado del repositorio (importante para la mañana)

- Todos los cambios de esta noche están COMITEADOS en la rama local
  `dtm-rasterio` (commits `dbfdb66`, `eaf2797`, `26095e3`).
- **NO se pudo hacer `git push`**: este dispositivo usa credenciales de
  GitHub de `escudero819`, y el repo (`github.com/AxelRoda202/
  repo_improvisado`) responde 403 (permiso denegado). Opciones:
  a) Axel empuja la rama desde SU dispositivo (donde sí tiene credencial),
  b) o Axel añade a `escudero819` como colaborador del repo,
  c) o se configura aquí una credencial de Axel (PAT) para el push.
- `git log --oneline` en `dtm-rasterio` debe mostrar la secuencia:
  optimización GDS (D+E) → piloto DTM → fix f-strings → integración A +
  caché de catálogos → endurecimiento del GDS. Si falta alguno, el
  trabajo de esta noche no está en esa máquina.

## 12. Ideas NO implementadas (por alcance, documentadas para no perderlas)

- Mosaico multi-tile para cajas grandes (hoy se usa 1 tile y la política
  de cobertura rechaza el resto; con mosaico, ±0.5° completos por DTM).
- Cráteres por segmentación del DTM (la heurística actual es de cribado:
  depresiones de >1.5σ; los candidatos de malla y de nube no son 1:1).
- TTL opcional en los catálogos (hoy sin caducidad, como la caché GDS).
- Diviner sigue siendo el cuello de botella frío (33-134 s según carga
  del servidor): no hay alternativa medida, es temperatura REAL.

---

# TERCERA SESIÓN (16 nov, rama `dtm-rasterio`): SOPORTE DE MARTE

**Pregunta que abrió la sesión:** "¿las fuentes abarcan también Marte? ¿por
qué `obtener_datos_sitio(cuerpo='marte', ...)` no trae datos?" Respuesta
corta: las fuentes SÍ (STAC de USGS tiene DTMs de CTX/HiRISE, Mars Trek
tiene capas), pero el colector solo traía CATÁLOGOS para Marte, no datos
puntuales, porque LOLA y Diviner son instrumentos lunares. Sesión: portar
la receta DTM a Marte con el MISMO formato de diccionario.

## 13. Sondas a las fuentes marcianas (lo medido contra lo real)

### 13.1 El GDS de PDS NO tiene Marte (sonda descartada)

- Presets probados con `gds_query`: `mola_rdr`, `molardr`, `mola`,
  `themisrdr`, `mgs_tes` en la caja de Jezero (±0.05 y ±1°): TODOS
  responden `error: 'Please include a query type'` (el GDS lunares no
  reconoce presets marcianos; su User's Manual solo cubre LOLA/Diviner
  y misiones lunares).
- El ODE IIPT sí lista 597 combinaciones de productos marcianos (TGO ACS,
  THEMIS, TES, CTX, HiRISE...), pero son descargas de productos crudos,
  no un servicio de estadísticas puntuales.
- **Veredicto: no hay 'GDS marciano'.** La vía puntual es el DTM del STAC.

### 13.2 El STAC de USGS SÍ tiene DTMs de Marte en Jezero ✅

- `usgs_stac.search(['mro_ctx_controlled_usgs_dtms', ...])` en Jezero:
  10+ items con bbox, asset en S3 estático:
  `.../P18_007925_1987_XN_18N282W__P19_008650_1987_XI_18N282W_dtm.tif`.
- **Diferencia con la Luna:** el asset de Kaguya termina en `-dem.tif` y
  el de CTX en `_dtm.tif` → el filtro de `topografia_dtm._tile_dem_para`
  ahora acepta ambos sufijos (`SUFIJOS_DEM_TIF`).
- Tamaño del tile CTX: descarga 4.2 s (sonda), lectura window-read igual.

### 13.3 La CRS marciana (el hallazgo técnico de la sesión)

- El tile CTX de Jezero usa **IAU_2015:49910**: 'Mars (2015) Sphere /
  Ocentric / Equirectangular' PROYECTADA en METROS (bounds ~4.6M,
  ~1.1M), a diferencia de los tiles Kaguya (geográficos, IAU_2015:30100,
  grados).
- PROJ de esta instalación NO puede transformar hacia/desde CRS de otros
  cuerpos: `IAU_2015:30000` no parsea ('The WKT could not be parsed') y
  hacia EPSG:4326 rechaza por mezclar Tierra↔Marte.
- Solución: **fórmula manual de la equirectangular** x = R·(λ-λ0)·cos(φ1),
  y = R·φ con R = 3.396.190 m (constantes.RADIO_DATUM_MARTE_M), leída de
  `src.crs.to_dict()` (proj='eqc', lat_ts=0, lon_0=0, R=3396190).
  VERIFICADA: bbox→metros exacto (window 882×882 px) e INVERSA exacta
  (metros→(77.58, 18.38) sin error). El inverso alimenta la lat/lon de
  los candidatos a cráter.
- Limite: tiles marcianos POLARES usan proyección estereográfica ('stere')
  → con esta instalación de PROJ no se pueden leer de forma segura; el
  código devuelve error claro + fallback honesto (sin dato puntual).

### 13.4 Gale no tiene DTM controlado (sonda)

- Buscada la caja de Gale (±0.15, ±0.5 y ±1.5°) en CTX/HiRISE DTMs:
  50 items, **0 tifs**. Los DTMs controlados solo existen en zonas
  mapeadas por USGS (Jezero sí, Gale no).
- Comportamiento del colector: sección topográfica en catálogos +
  `nota_elevacion` honesta + `dtm_descargables` (10 tiles de imagen/THEMIS
  listados). NUNCA se inventan números.

## 14. Integración de Marte en `api.py` (mismo formato, políticas propias)

- `topografia_dtm.analizar_sitio(..., cuerpo='moon'|'mars')`: radios de
  datum por cuerpo (RADIOS_DE_DATUM), filtro de sufijos DEM, transformación
  de caja PROJ-primeiro/manual-fallback, y conversión de cráteres a
  lon/lat con el inverso eqc.
- `_dtm_encadenado(cuerpo, ...)`: patrón idéntico al lunar (DTM encadenado
  al futuro del STAC, reutiliza items).
- Rama MARTE en `obtener_datos_sitio()`: pool de 3 hilos (Treks + STAC +
  DTM), sección topográfica con las MISMAS claves que la Luna
  (elevacion_m/pendiente/rugosidad/crateres_formaciones/dtm_detalle/
  dtm_descargables/capas_trek + `via='dtm_mro'`).
- **Política de cobertura RELAJADA para Marte: ≥50 %** (en la Luna ≥90 %):
  sin fallback GDS, un tile que cubra la mitad de la caja sigue siendo la
  única elevación puntual disponible. Cuando la cobertura es <90 % se
  añade `nota_cobertura` al dict (medido: Jezero ±0.5° → 68 %).
- Bug destapado y corregido: la ruta en serie `elif cuerpo != 'earth'`
  también ejecutaba para Marte → 'Treks' aparecía 2 veces en `fuentes`.
- Resumen del registro: mismas claves; con Marte `n_puntos_lola` cuenta
  PÍXELES del DTM (4.262.513 en Jezero ±0.5°) y `via_topografia='dtm_mro'`.
- Mapa geológico marciano añadido a constantes
  (URL_MAPA_GEOLOGICO_MARTE, Global Geologic Map of Mars 1:20M) para las
  referencias de `crateres_formaciones`.

## 15. Benchmark y calidad de Marte (medidos)

| Corrida (Jezero 18.38, 77.58) | Tiempo | Vía | Notas |
|---|---|---|---|
| Sonda tile frío (±0.15, tile nuevo) | ~6 s | DTM | descarga 4.2 s + STAC 2 s |
| Completa frío catálogos (±0.5, tile ya en disco) | **2.8 s** | dtm_mro | Treks mars + STAC a la red; el resto de disco |
| Completa tibia (±0.5, todo en caché) | **1.1 s** | dtm_mro | | 

| Métrica | Jezero ±0.15 | Jezero ±0.5 (cobertura 68 %) |
|---|---|---|
| Píxeles del DTM | 777.763 | 4.262.513 |
| Resolución | 20.2 m/px | 20.2 m/px |
| Elevación media | **-2607.3 m** | -2377.9 m |
| Rango elevación | -2699.9 … -2423.1 | -2699.9 … -1356.1 (borde del cráter) |
| Pendiente media | 2.27° | 4.74° |
| Rugosidad media (celdas ~100 m) | 1.11 m | 2.40 m |
| Píxeles válidos | 99.98 % | 72 % |

- La elevación media de ±0.15 (-2607 m) describe el PISO de Jezero
  (consistente con la literatura: el fondo del cráter ronda -2.6 km); la
  de ±0.5 (-2378 m) sube porque la caja pisa la ladera/borde oriental
  (max -1356 m). Ambas plausibles: la diferencia es GEOMETRÍA de la caja,
  no error.
- Pendiente media 2.3-4.7°: coherente con un terreno de cráter + deltas
  excavados. Rugosidad ~1-2 m moderada.
- Sin datos reales de 'verdad terreno' para comparar (no hay LOLA
  marciano): la verificación fue contra la CRS (inversa exacta) y la
  plausibilidad geológica. Un contraste futuro: muestrear la capa DEM de
  Mars Trek en la misma caja.
- Regresión lunar verificada tras los cambios: Smythii tibio 4.2 s,
  mismos números (-2325.34 / 3.731 / 1.932), vía dtm_kaguya intacta.

## 16. Estado del soporte por cuerpo (resumen de las 3 sesiones)

| Cuerpo | Topografía | Térmico | Superficie/Iluminación | Fallback |
|---|---|---|---|---|
| Luna | DTM Kaguya (malla 19-30 m) o LOLA GDS | Diviner GDS (real, 9 canales) | Treks + Clementine | DTM→LOLA (política ≥50 % px, ≥90 % cobertura) |
| Marte | DTM CTX/HiRISE (malla ~20 m) o catálogos | THEMIS/TES (capas; sin puntual) | Treks (CRISM/Ω) | sin DTM→nota honesta |
| Tierra | análogos_tierra (CMR/GIBS) | GIBS | Copernicus | — |

## 17. DB local de sitios marcianos (`db_sitios_marte.py`) — 4ª sesión

Pedida para dejar de adivinar: "¿qué lugares de Marte tienen datos?" pasa
de sondeo manual a una lista consultable. La DB indexa lugares CON NOMBRE
del Gazetteer y guarda topografía (formato de comparación) + metadatos de
disponibilidad THEMIS (ventana ≤ 1 mes, nunca valores inventados).

### 17.1 Sondeos previos (los que decidieron el diseño)

| Sondeo | Resultado | Consecuencia de diseño |
|---|---|---|
| Conteo total de la colección CTX del STAC (paginada) | **44.628 items** (todos con `start_datetime`), 172.8 s, y el HiRISE dio 502 por la carga | NO indexar por tiles: imposible enriquecer 44k y el STAC no aguanta. Indexar por LUGARES |
| `/vsicurl/` + window read del tile CTX de Jezero | 882×882 px, media -2607.3, **6.3 s** — mismos números que el fichero bajado | Los stats se calculan leyendo el trozo por HTTP: cero descargas de tiles |
| `format=CSV` del Gazetteer | Param solo-cliente: el CSV lo arma el JS en el navegador | Parsear la tabla HTML `search_results` con regex |
| Gazetteer sin filtro (`PageSize=500`) | **2.100 lugares de Marte en UNA página**, 3.1 s | 1 GET para toda la lista |
| Combos ODE (IIPT) | `ODY/THEMIS/IRBTR4` válido (PDS4, con fechas de obs) | Fuente de mediciones múltiples |
| ODE `Count` con limit 200/500 | Devuelve tantas filas como el límite; Jezero ±0.1° = 211 obs reales, rango 2002-02-28 → 2026-02-26 (THEMIS sigue activo) | límite 500; el total real = longitud de la lista |
| ODE PDS4: `Id`/`Start_time` | `None`; los datos están en `Observation_time`, `Solar_time` y el id en `FilesURL?product_id=` | `ode_products` extendido (`_id_de_url`, observation_time, solar_time) |
| Ventana de 31 días en Jezero | Solo 1 obs de 211 (2026-02-26) | Guardar TODOS los ids de la ventana (aunque sea 1): honestidad > volumen |

### 17.2 Diseño

- **Filtro de indexado** (`indexar_gazetteer`): 2.100 filas − 127 'Albedo
  Feature' (sin relieve) − 840 cráteres < 40 km (el DTM de 20 m/px no
  resuelve bien cráteres chicos y serían cientos de lecturas al cuete) →
  **1.133 sitios 'pendiente'** (410 cráteres ≥ 40 km + 723 otras
  formaciones: 159 valles, 64 montes, 37 plana, 34 pateras...). Verificado
  que entran Jezero (47.5 km), Gale (154 km), Olympus Mons, Hellas.
- **Radio de la caja**: cráteres = diam/2 → grados (1°≈111.32 km)
  corregido por cos(lat), recortado a [0.05, 0.5]°; resto de tipos 0.2°
  fijo (los diámetros de planitiae/valles son de cuenca completa:
  Hellas 2.299 km → una caja así no se puede analizar).
- **Convenio de longitudes**: el Gazetteer trae 0-360 Este → a [-180, 180]
  (`lon-360` si >180).
- **Enriquecimiento** (`enriquecer`): por sitio, 1 búsqueda STAC por bbox
  (cacheada) + `analizar_sitio(..., modo_tile='remoto')` + ODE
  IRBTR4 limit=500 (cajas 0-360 con `utilidades.cajas_gds`, por si cruza
  el meridiano 0). Resumible: solo procesa 'pendiente'.
- **Política de cobertura: la MISMA que api.py** (relajada ≥ 50 %):
  `confiable AND cobertura ≥ 0.5` para ser 'listo'; si no, 'sin_dtm' con
  el motivo (p.ej. "cobertura 5% / píxeles válidos 99% < política 50%").
  Si el tile cubre <90 % queda `nota` (mismo texto que `nota_cobertura`).
- **Estados**: pendiente → listo | sin_dtm (no hay tile o cobertura
  insuficiente) | error (otra causa). `reintentar [--todo]` devuelve a
  pendiente.
- **Ventana THEMIS**: [última obs − 31 días, última obs]; en `mediciones`
  van SOLO los productos de la ventana (id, fecha, hora solar). En
  `sitios.themis_n_obs` queda el total de la caja como metadato de
  disponibilidad.
- **SQLite**: `data/db/sitios_marte.db` (data/ gitignored, como las
  cachés). Tabla `sitios` + tabla `mediciones` PK(sitio_id, producto_id).
  Hilos 2-3 máx con lock de escritura (conexión por transacción).
- **Salida** (`sitios_disponibles`): dicts con `resumen` de EXACTAMENTE
  las claves del registro del proyecto (elevacion_media_m,
  pendiente_media_grados, rugosidad_media_m, n_puntos_lola=píxeles,
  via_topografia='dtm_mro') + `topografia_extra` + `mediciones` (metadatos
  de la ventana). Los consumidores enchufan `resumen` tal cual.

### 17.3 Medido (sesión 4)

| Paso | Tiempo | Resultado |
|---|---|---|
| `indexar` (Gazetteer completo) | 1.6 s | 2.100 filas → 1.133 sitios |
| Lote 6 sitios, 2 hilos | 11.8 s | 1 listo, 5 sin_dtm (cajas al azar del ecuador: los DTM CTX/HiRISE cubren ~5 % de Marte) |
| Lote 8 sitios siguientes | 2.6 s | 0 listo, 8 sin_dtm (sin tile: fallo rápido, no hay red de más) |
| Jezero directo (`_enriquecer_sitio`) | ~10 s | listo: 20.2 m/px, cobertura 97.5 %, 231 obs THEMIS, 2 en ventana 2026-01-27..02-27 |
| End-to-end DB→`obtener_datos_sitio` | 0.7 s (tile en caché) | NÚMEROS IDÉNTICOS (elev -2599.497, pend 2.374) y mismo tile → la DB es un menú válido |

- La proporción 'sin_dtm' es ALTA (~90 % en los primeros lotes): es la
  cobertura real de los DTM controlados del MRO. Por eso la DB es útil:
  evita que el usuario pruebe caja tras caja sin datos.
- **Corrida final completa** (2 tandas por corte del shell de fondo;
  resumible como estaba previsto): 1.133 sitios en ~25 min de red, **0
  errores**. Resultado: **199 'listo'** (17,6 % — la cobertura real de
  los DTM controlados del MRO, ~5 % de la superficie pero coinciden con
  los lugares famosos), **934 'sin_dtm'** con motivo guardado. 328
  mediciones THEMIS en las ventanas; los 199 listos tienen TODOS ≥ 1 obs
  en su ventana (THEMIS sigue activo). Muestras plausibles: Apollinaris
  Tholus +1.634 m, Bamberg (cráter) piso -5.057 m, Acheron Fossae +106 m.
- `listar` con solo_listos devuelve los 199 en formato de comparación,
  listos para ser el menú de la app.

### 17.4 Soporte tocado en esta sesión

- `topografia_dtm.analizar_sitio(..., modo_tile='remoto')`: NO descarga
  el tile; abre `/vsicurl/{url}` y lee solo la ventana. Verificado contra
  el tile bajado: mismos números. `out['acceso']='remoto (vsicurl)'`.
- `pds.ode_products`: lee `Observation_time`/`Solar_time` y saca el id de
  `FilesURL?product_id=` (`_id_de_url`) — los PDS4 venían con id/fecha
  nulos.
- `db_sitios_marte.py`: NUEVO módulo (indexar/enriquecer/listar/
  reintentar/estado, CLI incluido).

---

# CUARTA SESIÓN (15 nov, ramas `tierra-datos-crudos` + `tierra-glo90-rapida`):
# DATOS CRUDOS DE LA TIERRA EN EL MISMO FORMATO QUE LUNA Y MARTE

**Pregunta que abrió la sesión:** la Tierra era el pariente pobre del
colector — `obtener_datos_sitio('tierra', ...)` devolvía solo CATÁLOGOS
(nombres/ids de colecciones CMR, escenas, capas GIBS) mientras Luna y Marte
devuelven NÚMEROS crudos por sección. Objetivo: paridad de formato sin
credenciales obligatorias. **ESTADO: COMPLETADO y verificado end-to-end.**

## 18. Ruta ejecutada (paso a paso, cada paso = 1 commit)

| Paso | Qué | Fuente elegida | ¿Auth? | Medido |
|---|---|---|---|---|
| 1. Topografía | elevación/pendiente/rugosidad/cráteres | **Copernicus DEM GLO-30** (bucket AWS público, tile 1°×1°, ~30 m/px) | NO | frío 43-196 s (red lenta; varía) / tibio **0.07 s** |
| 2. Térmico | TS en K + día/noche + estacional | **NASA POWER** (MERRA-2, 2 peticiones JSON ~2 s) | NO | **3.2 s** |
| 3. Superficie | reflectancia visible + NDVI + máscara SCL | **Sentinel-2 L2A via Earth Search** (Element84, COG en AWS abierto) | NO | frío ~42 s (5 bandas remotas) / tibio **1.3 s** |
| 4. Iluminación | fracción diurna + energía solar | **cálculo local** (geometría solar, 0 llamadas) | NO | <1 s |
| 5. Integración | `api.py`: mismas secciones que luna/marte | pool de 3 hilos | — | tibio **~5 s** |
| 6. Verificación | comparación lado a lado de `resumen` | `prueba_tierra_comparacion.py` | — | ver §19 |

Sondas descartadas en el camino (medidas contra la red real):
- **Landsat C2 L2** (landsatlook STAC público, 1.8 s, escenas recientes):
  los COG redirigen al login de EROS (ERS) → requiere cuenta gratuita.
  Descartada para la vía sin-credenciales.
- **MOD11A2 (MODIS LST 1 km)**: HEAD responde 200 pero el GET real da
  **401 "HTTP Basic: Access denied"** (rutas `lp-prod-protected`). OJO:
  el HEAD MIENTE; siempre probar con un GET de rango. Queda como vía
  MEJORADA opcional (ver §21).
- El primer sonda térmico eligió por error una colección FEDEO/INPE (0
  granules con bbox): **filtrar siempre por proveedor `-LPCLOUD`**.

## 19. Resultado final: paridad de formato (tabla comparada real)

`python -m colector_datos.prueba_tierra_comparacion --luna_completa`
(15-nov-2026, este dispositivo):

| Clave del resumen | TIERRA Atacama | LUNA Smythii | MARTE Jezero |
|---|---|---|---|
| elevacion_media_m | **+1564** | -2325 | -2610 |
| pendiente_media_grados | **4.72** | 3.73 | 2.27 |
| rugosidad_media_m | **2.69** | 1.93 | 1.11 |
| temperatura_media_k | **292** | 230 | — (sin GDS marciano, nota) |
| diferencia_dia_noche_k | **19.2** | 193 | — |
| variacion_estacional_k | **11.1** | 241 | — |
| reflectancia_media | **0.199** | 0.111 | — (capas Treks) |
| energia_solar_media_wm2 | **573** | 799 | — |
| fraccion_diurna | **0.5** | 0.587 | — |
| n_puntos_lola | **129 600** (px GLO-30) | 12 978 (px Kaguya) | 777 763 (px CTX) |
| n_observaciones_diviner | **8760** (horas POWER) | 14 395 | — |
| via_topografia | **glo30** | dtm_kaguya | dtm_mro |
| Tiempo de pared | 5.1 s tibio | 48.9 s frío | 0.6 s tibio |

Mismas claves, mismas unidades (K, m, °, 0-1, W/m²) → la comparación 1:1
y la puntuación de análogos ya puede consumir los tres vectores igual.

## 20. Complicaciones encontradas y CÓMO SE RESOLVIERON (registro)

1. **Convención de nombres de tile GLO-30**: no es `W70_00` sino
   `W070_00` (longitud SIEMPRE con 3 dígitos; latitud con 2). Destapado
   porque Atacama daba 404 con la convención "obvia" y Death Valley 200.
   El bucket además ES LISTABLE (GET con `list-type=2`) — útil para
   verificar cobertura sin STAC.
2. **Tiles de océano puro NO existen** (404 del bucket): p.ej. 35°N 35°W.
   No es un fallo de red: se traduce a un mensaje claro ("sitio en mar
   abierto") en `topografia_tierra.analizar_sitio`.
3. **El tile GLO-30 es band-strided (NO COG en teselas)**: la lectura
   remota /vsicurl de una ventana de 360×360 hace ~360 peticiones de rango
   (medido ~17-22 s) — al revés que Kaguya/CTX (COG, ventana en ~6 s).
   Por eso en la Tierra la vía por defecto es DESCARGAR el tile completo
   y cachearlo (tibio 0.07 s). La vía 'remoto' sigue disponible con
   `modo_tile='remoto'`.
4. **Sentinel-2 en UTM**: window read directo con lon/lat da ventanas
   vacías (0×0). Hay que transformar la caja de EPSG:4326 a la CRS del
   tile (`rasterio.warp.transform`) — en la Tierra PROJ funciona, sin
   trucos IAU.
5. **La banda SCL va a 20 m y las bandas a 10 m**: la máscara hay que
   sobremuestrearla 2×2 (vecino más próximo) o salta un error de broadcast.
6. **`rasterio.warp` no viene con `import rasterio`**: importar
   explícitamente (falló en la primera corrida de Sentinel).
7. **Bug real corregido en `nsac/sources/earthdata.py`**: CMR devuelve
   `granule_size` como float ("6.444...") y `int()` casca — ahora `float()`.
   Descubierto al buscar granules de MOD11A2 (búsqueda 200 sin auth, 0.2 s).
8. **Landsat vs Sentinel-2 en cabeceras**: HEAD de LandsatLook 302 → HTML
   de login; GET con rango confirma. Lección: **no fiarse del HEAD** para
   decidir si un recurso es abierto.
9. **Rugosidad falsa a 90 m/px** (GLO-90): una celda de 100 m contiene
   1 píxel → std = 0 ("terreno liso" falso). Corregido con celda mínima de
   2 píxeles por lado (Atacama 90 m: 3.19 m en celdas de 177 m vs 2.69 m
   en celdas de 113 m del GLO-30 — coherente).
10. **Varianza de POWER**: la media anual de TS para Death Valley dio
    294.171 K en dos corridas y 291.771 K en una intermedia (n=8760 igual
    en todas). Es un reanálisis vivo: puede refrescar sus series. No es
    un bug del colector; no comparar con más de 1 decimal.

## 20-bis. Sub-rama `tierra-glo90-rapida` — comparativa de fríos (medida)

Mismo sitio, primera visita SIN caché (nov-2026, red de 0.2-0.7 MB/s):

| Sitio | GLO-30 frío (37-42 MB) | GLO-90 frío (4-5 MB) | Δ elevación | Δ pendiente |
|---|---|---|---|---|
| Atacama ±0.05 | 43.6 s (hasta 196 s) | **8.6 s** | 0.05 % | 4.72° → 3.90° |
| Death Valley ±0.1 | 61.5 s | **7.3 s** | 0.33 % | 19.0° → 15.8° |
| Haughton ±0.2 | 22.0 s | **2.2 s** | ~0 % | 5.79° → 4.87° |

- Elevación: acuerdo excelente (la media no depende de la resolución).
- Pendiente/rugosidad: GLO-90 "suaviza" el terreno corto — la misma
  relación dirección-resolución que LOLA vs DTM Kaguya (§9.1): NO son
  intercambiables 1:1 para "¿se puede aterrizar?".
- Veredicto: **GLO-30 sigue siendo el valor por defecto** (fidelidad para
  el análogo definitivo); GLO-90 es la vía de CRIBA rápida cuando hay que
  fríos-teclear MUCHOS sitios. Activar con
  `topografia_tierra.analizar_sitio(..., resolucion='90m')`.
- Ambas conviven en la misma rama (la sub-rama se fusionó --ff-only al
  quedar aditiva y retrocompatible: por defecto sigue '30m').

## 21. Credenciales (solo si se quiere la vía mejorada, NO obligatorias)

Todo lo anterior funciona **sin ninguna cuenta**. La única mejora que
requiere credenciales es el térmico de 1 km real (MOD11A2 en vez del
reanálisis POWER de ~50 km):

1. Crear cuenta gratuita en https://urs.earthdata.nasa.gov/users/new
   (aceptar las Apps de LP DAAC en el perfil: "Approve Applications").
2. Copiar `.env.example` a `.env` y rellenar:
       EARTHDATA_USERNAME=<usuario>
       EARTHDATA_PASSWORD=<contraseña>
3. Las peticiones autenticadas usarían `earthaccess` (ya en
   requirements.txt, auth extra de `.env`); el resto del colector no las
   toca. Pendiente de implementar: descargar el granule HDF (401 sin
   credenciales, verificado) y leer `LST_Day_1km`/`LST_Night_1km` con
   rasterio (comprobar que el wheel trae el driver HDF4-EOS).
   Otras cuentas que el proyecto ya contempla en `.env.example`:
   CDSE (descargas Sentinel-1/2/3 de Copernicus) y JAXA G-Portal.

## 22. Estado y pendiente (para la siguiente sesión)

- Hecho: paridad completa de formato tierra/luna/marte; 6 commits en
  `tierra-datos-crudos` (pasos 1-6) + 1 en la sub-rama fusionada.
- Pendiente opcional: MOD11A2 con Earthdata (§21); aerosol MODIS/Sentinel-5P
  para "polvo" terrestre; humedad SMAP (requiere Earthdata también);
  mosaico multi-tile GLO-30 para cajas que pisan 2 tiles en el
  antimeridiano (hoy se reporta cobertura < 1).
- La rama `tierra-datos-crudos` NO está en `master` (igual que
  `dtm-rasterio`): falta revisión/push (NOTAS §11).

## 23. Rama `supabase-candidatos` — carga masiva ±0.05° + DB de análogos en la nube

**Fecha:** 15-nov-2026. Objetivo: alimentar la fase de evaluación con un
catálogo de sitios candidatos a ±0.05° en el registro local y un buscador
de similitud ponderada (K-NN) en Supabase.

### 23.1 Qué se construyó (los 3 entregables + soporte)

- `supabase/esquema_rpc.sql` — entregable 1, para el SQL Editor del panel:
  tabla `sitios_candidatos` (claves del resumen unificado 1:1), tabla
  `parametros_escalas` (rangos físicos de normalización, afinables sin
  tocar la función), `calcular_similitud(perfil_ideal JSONB, datos_lugar
  RECORD)` (distancia euclidiana inversa 0..1: NULL = "la fuente no dio
  el dato" → ese parámetro se EXCLUYE y los pesos se renormalizan solos
  al dividir por suma_pesos) y RPC
  `buscar_analogos_ponderados(parametros JSONB, objetivo_espacial TEXT)`
  (Top 1 extraterrestre fuera del cuerpo objetivo + Top 5 Tierra).
  Idempotente (re-ejecutar no pisa los rangos afinados ni los datos).
- `colector_datos/poblador_supabase.py` — entregable 2: fusiona
  `data/registro_sitios.json` + `data/db/sitios_marte.db` por `sitio_id`,
  salta filas todo-NULL (nunca devolverían similitud) y sube por lotes de
  100 con `on_conflict='sitio_id'` (upsert resumible).
  `lanzar_en_segundo_plano()` lo corre en un hilo daemon invocable desde
  `ejemplo_uso.py --poblar_nube`. CLI: `simular` (mapping sin red),
  `poblar`, `estado`.
- `colector_datos/prueba_similitud_nube.py` — entregable 3: cliente del
  RPC con payload de pesos (default 80 % pendiente / 20 % elevación),
  `--perfil` JSON libre o `--perfil-desde 'clave@...±...'` (deriva el
  perfil de un sitio real del registro con pesos equitativos).
- `colector_datos/cargador_sitios.py` — la carga masiva al registro local
  (NO a la nube: la nube se puebla desde el registro). Saltar lo ya
  cargado, pool de hilos, tierra vía GLO-90 por defecto (`--glo30` para
  fidelidad), bandera `--gds` para caracterizar polos lunares completos
  (Diviner+LOLA vía GDS, minutos; con ella `--hilos 1`).
- `constantes.CATALOGO_ANALOGOS_TIERRA` — 12 análogos terrestres clásicos
  (Atacama, Death Valley, Salar Grande, Pajonales, McMurdo-Taylor,
  Haughton, Krafla, Mojave, Namib-Gobabeb, Lut-Shahdad, Qaidam, El Tatio).

### 23.2 Bugs encontrados y arreglados en esta rama

- **Carrera del registro (REAL, mordió):** `guardar_en_registro` hace
  leer-modificar-escribir del JSON entero; con el pool de 3 hilos de la
  carga masiva, dos escritores se pisaron y el registro perdió 2 entradas
  PREEXISTENTES (`moon@-23.4,157.8±0.05`, `mars@18.38,77.58±0.15`):
  último escritor gana. Fix: `_LOCK_REGISTRO` (threading.Lock) en
  `api.py` serializa SOLO la sección crítica; las consultas siguen en
  paralelo. Ambas entradas restauradas (tibias, segundos).
- **Vía DTM lunar anclada a `usar_gds`:** el pool lunar solo arrancaba
  con `usar_gds=True`, así que `usar_gds=False` dejaba la Luna SIN
  topografía (contradecía el docstring, que promete DTM en segundos).
  Fix: el pool corre con `(usar_gds or usar_dtm)` y Diviner/LOLA solo con
  `usar_gds`. Verificado: Smythii `via=dtm_kaguya` en 9.1 s con resumen
  completo. Consecuencia para los polos: Kaguya no los cubre (huecos de
  sombra, §9) y sin GDS quedan honestos pero sin métricas → bandera
  `--gds` del cargador para completarlos (corrida aparte, minutos).
- **Refactor del lock con error propio:** la primera versión del helper
  `_guardar_en_registro_bajo_lock` no recibía `m` (metadatos) → el
  registro devolvía "no se pudo guardar: name 'm' is not defined" y
  NADA se escribía (19→17). Lección: tras un refactor, verificar con una
  consulta real que el registro crece, no solo que el import pasa.
- **Cuerpo en dos idiomas:** el registro usa los códigos internos
  `earth/moon/mars` (de `utilidades.normalizar_cuerpo`) y la tabla de
  Supabase usa `tierra/luna/marte` (check del SQL). Fix en el poblador:
  mapa inverso `_CUERPO_ES` al subir (antes `nombre: null` y, peor, el
  check habría rechazado TODAS las filas del registro).

### 23.3 Mediciones de la carga (frío→tibio)

- Catálogo completo: 19 sitios (tierra=12, luna=4, marte=3) en ~233 s.
- Tierra vía GLO-90: tibio 4.6-11.9 s; frío 60-107 s (S2 cold es el techo).
- Luna vía DTM (no polares): Smythii 9.1 s `dtm_kaguya`. Polares sin DTM:
  fallback honesto sin números con `usar_gds=False`; con `--gds --hilos 1`
  ≈ 1-2 min/sitio (PENDIENTE de correr: shackleton/malapert/peary con
  Diviner+LOLA).
- Marte: Jezero 2.3 s `dtm_mro`; Gale/Extranio sin DTM controlado → sin
  métricas (comportamiento esperado, honesto).
- Tibio total (todo cacheado): ~12 s para 19 sitios (no medido separado;
  estimado de los tibios individuales).

### 23.4 Decisiones Supabase (para el SQL del panel)

- Normalización por RANGOS FÍSICOS en `parametros_escalas` (una fila por
  parámetro; re-ejecutar el SQL NO pisa rangos afinados). La similitud es
  `1 - sqrt(sum(w_i * d_i²) / sum(w_i))` con `d_i = (v_i - objetivo_i) /
  rango_i`, recortada a [0,1].
- `sitio_id` (la clave del registro, con `±` unicode) es UNIQUE y sirve
  de `on_conflict` del upsert: repetir la carga ACTUALIZA (misma pauta
  que el registro local).
- `fecha_consulta` se guarda como TEXT tal cual vino (ISO del registro):
  no se inventa un timestamptz parseado.
- `extra JSONB` recoge lo que no es columna (mediciones THEMIS, fuentes).
- El RPC devuelve JSONB único (`extraterrestre_top1` + `tierra_top5` +
  diagnóstico): una sola ida y vuelta para el cliente de prueba.
- Credenciales: `SUPABASE_KEY` = **service_role** (sk_...) SOLO en
  `.env` local; el `anon` key no puede escribir sin RLS abierta.

### 23.5 Estado de la rama y pendiente

- Verificado sin red: `poblador simular` (19 filas mapeadas, tierra=12,
  luna=4, marte=3, nombres resueltos, cuerpo en español);
  `prueba_similitud_nube` → error claro sin credenciales;
  `ejemplo_uso --rapido --poblar_nube` → prechequeo de credenciales y
  mensaje determinista (el hilo daemon moría con el proceso sin imprimir).
- `requirements.txt`: `supabase` y `python-dotenv` pasan a obligatorios.
- Pendiente del usuario: ejecutar `supabase/esquema_rpc.sql` en el SQL
  Editor, rellenar `.env` (URL + service_role) y correr
  `python -m colector_datos.poblador_supabase poblar` +
  `python -m colector_datos.prueba_similitud_nube`.
- Pendiente opcional: polos lunares con `--solo luna --gds --hilos 1`
  (Diviner frío ~1-2 min/sitio; daría térmico + LOLA a shackleton,
  malapert y peary).
- Push: 403 con la credencial de este dispositivo (§11); Axel empuja.

### 23.6 `carga_fondo.py` — orquestador para llenar TODO (día siguiente)

Pedimento: "dejar en segundo plano cargando todos los lugares de tierra y
marte". Nace `colector_datos/carga_fondo.py`: 1 comando reanudable
(Ctrl+C no pierde nada) que encadena las fases reutilizadas, sin
reescribirlas:

  1. TIERRA   `cargador_sitios.cargar('tierra')` (salta lo ya cargado).
  2. GAZETTEER `db_sitios_marte.indexar_gazetteer()` SOLO si la DB está
     vacía. Medido: 2.100 lugares parseados en 3.7 s -> 1.133 útiles
     (840 cráteres filtrados por diámetro, 127 albedo excluidos).
  3. MARTE    bucle `enriquecer(--lote)` hasta agotar 'pendiente'; tras
     CADA lote, `poblar()` sube lo nuevo a Supabase (upsert: la nube
     crece mientras el fondo trabaja). Ritmo medido: 0.5 s/sitio donde
     no hay tile, ~8 s/sitio con DTM+THEMIS -> 1.133 sitios ≈ 1-2 h.
  4. REINTENTO una pasada extra para los 'error' (red); 'sin_dtm' queda
     como está (honesto: no hay tile).
  5. CIERRE   poblar final + estado.

Flags: `--hilos` (default 3), `--lote` (default 50), `--saltear_tierra`,
`--saltear_marte`, `--sin_nube`, `--refrescar_tierra`.
Smoke real: `--lote 2 --hilos 2` -> gazetteer indexado, 3 sitios
enriquecidos (1 listo, 5 sin_dtm), y subidas a la nube `+20 -> +21`
CONFIRMA que la service_role key del usuario ya escribe (el 42501 quedó
resuelto cambiando publishable por secret).

## 24. Luna con la funcionalidad de marte + APIs v2 + guardián de Supabase

**Pedido:** "implementar la funcionalidad que tiene marte con la db
también a la luna" (gazetteer -> DB local -> nube), APIs propias por
cuerpo (luna/marte top-1 individual; tierra flexible con similitudes por
categoría), investigar el límite de Supabase y cargar en fondo
respetándolo con sectorización por prioridad.

### 24.1 Límite de Supabase (investigado, 15-nov-2026)

- Plan Free: **500 MB de base de datos por proyecto** (+ 1 GB file
  storage, 2 proyectos). Al superar 500 MB: avisos y, tras gracia,
  posibles restricciones (read-only / pausa / errores 402).
- Tamaño REAL de nuestro catálogo: ~0.3-0.5 KB por fila de
  `sitios_candidatos` -> 1.133 marcianos + ~2.090 lunares + 12 terrestres
  ≈ **1-1.5 MB**. No hay riesgo con filas de resumen; el guardián existe
  para el día que se suban series u otras tablas.
- **Guardián implementado**: RPC `uso_bd()` (security definer; bytes de
  base, bytes de tabla y nº filas). `poblar()` lo consulta al inicio y
  antes de CADA lote; límite de trabajo 450 MB (env
  `NSAC_SUPABASE_LIMITE_MB`); al llegar, corta LIMPIO (lo subido queda;
  repetir continúa). Degradación honesta: si el RPC no existe (falta
  rpc_v2.sql), avisa y sigue sin guardián.
- **Sectorización por prioridad**: `filas_unificadas()` ordena
  tierra -> luna -> marte (SECTOR_PRIORIDAD): si el guardián corta, lo
  valioso ya está dentro. "Adaptar el rango de tiempo de la tierra" no
  aplica hoy (las filas de tierra son resúmenes estáticos, no series);
  si un día hay series, el mecanismo límite+prioridad ya está en pie.

### 24.2 `db_sitios_luna.py` (paridad con `db_sitios_marte`)

- Gazetteer: `Target=16_Moon` (¡NO 10_Moon! sondeado: la página del
  buscador lista 16_Moon), PageSize=500 trae la página entera: **24 MB,
  9.202 lugares parseados en 3.9 s** -> **2.081 insertados** tras excluir
  los 7.114 'Satellite Feature' (epónimos de cráteres satélite "Walther
  A": denso y poco útil). En la Luna TODOS los cráteres con nombre
  entran (sin filtro de 40 km: el Kaguya DTM de ~10-30 m/px los
  resuelve; el total queda comparable a Marte).
- Enriquecimiento vía `topografia.dtm_disponibles('moon',...)` +
  `topografia_dtm.analizar_sitio(cuerpo='moon', modo_tile='remoto')`.
  **Política RELAJADA (>=50% píxeles válidos y >=50% cobertura, con nota
  honesta), la misma de la DB marciana** — NO la estricta de api.py
  (>=90% cobertura): las cajas del gazetteer (0.05-0.5°) no siempre caben
  enteras en los tiles Kaguya (Lansberg: 67% cobertura con 94% de
  píxeles válidos — los 4 primeros sitios salieron sin_dtm POR ERROR y
  se reencolaron a mano tras corregir la política; lección: la política
  de api.py es para cajas de ±0.05°).
- Ritmo medido: ~5 s/sitio con 3 hilos -> **2.067 pendientes ≈ 1 h**.
  Los sin_dtm de polos (huecos de sombra) y de cajas sin tile quedan
  honestos fuera.
- Esquema gemelo al marciano (sin themis_*/mediciones) -> los
  consumidores (`sitios_disponibles`, poblador) leen las dos DBs con el
  MISMO código (`_filas_de_db_gazetteer(modulo, cuerpo)`).

### 24.3 APIs v2 (`supabase/rpc_v2.sql`, a pegar en el panel DESPUÉS del esquema base)

- `similitud_ponderada(perfil JSONB, datos JSONB)`: la fórmula euclidiana
  inversa GENÉRICA (recorre el perfil con jsonb_each; nada de bloques por
  columna). NULL en la fila = parámetro excluido, pesos renormalizados
  (regla de oro). Guardia anti-NaN.
- `similitudes_por_categoria(perfil, datos)`: similitud INDEPENDIENTE por
  categoria (topografia/termico/superficie/iluminacion, cada una
  renormaliza SUS pesos) + 'global'. Con una fila sin datos de una
  categoría -> NULL (no se inventa).
- `buscar_analogo_cuerpo(parametros, cuerpo, topn=1)`: API PROPIA de cada
  cuerpo (luna/marte/tierra): Top N con desglose por categorías.
- `buscar_analogos_v2(parametros)`: UNA llamada -> luna_top1 + marte_top1
  (individuales, cada uno por su API interna) + tierra_top5 (flexible,
  con categorías) + conteos 'vistos'.
- `uso_bd()`: el guardián de §24.1.
- Cliente: `prueba_similitud_nube` ahora llama v2 por defecto (y
  `--cuerpo luna --topn 3` para la API de un cuerpo); imprime el desglose
  global/topografia/termico/superficie/iluminacion por fila.

### 24.4 Estado y pendiente

- Hecho y verificado localmente: DB lunar indexada (2.081, 2.067
  'pendiente' tras el smoke), 10+ sitios lunares 'listo' con DTM real,
  poblador fusiona las 3 fuentes con prioridad (simular: tierra=12,
  luna=17, marte=5).
- **Pendiente del usuario**: pegar `supabase/rpc_v2.sql` en el SQL Editor
  (el cliente y el guardián lo necesitan) y dejar corriendo
  `python -m colector_datos.carga_fondo --saltear_tierra --saltear_marte`
  para la fase lunar (~1 h) — o el comando completo para ambas.
- Pendiente opcional: polos lunares con térmico real (Diviner vía GDS,
  `cargador_sitios --solo luna --gds --hilos 1`).

## 25. Muestras de tierra completadas + fondo total en marcha

**Pedido:** "subime unas muestras de la tierra, y de ahi dejamos en
segundo plano todo".

- RPCs v2 verificadas tras el re-paste del usuario: `buscar_analogo_cuerpo`
  (luna top-2: Purkyně 0.993 / Van Vleck 0.991) y `buscar_analogos_v2`
  (luna_top1 + marte_top1 Kasabi + tierra_top5) responden sin errores.
- Catálogo de tierra expandido a 24 análogos (12 nuevos: Uyuni, Dallol,
  Río Tinto, Wadi Rum, Lonar, Meteor Crater, Kilauea, Shark Bay, Pilbara,
  Svalbard, Makgadikgadi, Pinacate; constantes.py, commit c99b90b).
  Carga vía `cargador_sitios --solo tierra`: fríos 50-108 s c/u (GLO-90,
  tile cacheado) / tibios 3.8-4.9 s.
- Poblador: 140 filas en la nube (tierra=24 con las 9 métricas, luna=63,
  marte=53), upsert 5.6 s, sin errores; guardián: base 11.4 MB
  (0.29 MB la tabla), 2.3% del límite de trabajo de 450 MB.
- RPC de tierra con perfil de 5 métricas: desglose por categorías llena
  (Salar Grande 0.937 global, topo=0.94, term=0.89) — los análogos nuevos
  rankean dentro del Top 5 (Wadi Rum 0.933).
- Fondo lanzado en segundo plano (sesión del agente): `carga_fondo
  --saltear_tierra` completo, log en Temp\opencode\carga_fondo.log.
  Reanudable: si muere, repetir el comando continúa donde quedó.
