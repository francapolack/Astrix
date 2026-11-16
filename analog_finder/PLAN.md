# PLAN — Analog Finder

## 1. Objetivo

Aplicación de escritorio en Python + Flet que encuentra sitios de la Tierra
análogos a la Luna (polo sur) o a Marte (Jezero), explica en qué se parecen,
dónde falla la analogía y para qué servirían en una misión.

La versión inicial usa **datos de ejemplo claramente señalizados**. La capa de
datos queda aislada para poder reemplazarla por CSV/JSON de fuentes abiertas sin
tocar la interfaz.

## 2. Entorno verificado (14/11/2026)

- Windows, Python 3.13.14.
- `flet==1.1.2`, `flet-desktop==1.1.2`, `flet-cli==1.1.2`.
- `flet-map==1.1.2` disponible y compatible con Flet 1.1.2.
- API de Flet 1.x confirmada contra los paquetes instalados:
  - `ft.run(main)` para iniciar la app.
  - `ft.Button` existe; también `ft.FilledButton`, `ft.OutlinedButton`,
    `ft.TextButton`.
  - `ft.Dropdown` usa `on_select` (no `on_change`).
  - La barra de progreso es `ft.ProgressBar`; no existe
    `ft.LinearProgressBar` en esta versión.
  - Tema Material 3 mediante `ft.Theme(use_material3=True, ...)`.
  - Ventana: `page.window.min_width` / `page.window.min_height`.
- `flet-map` expone `Map`, `TileLayer`, `MarkerLayer`, `Marker`,
  `MapLatitudeLongitude`, `CameraFit`.
- Nota de entorno: el ejecutable `flet.exe` está instalado en la carpeta
  `Scripts` del usuario pero esa carpeta no está en el PATH de esta terminal.
  Para correr la app se usa la ruta absoluta al ejecutable.
- `pytest==9.2.0` instalado y declarado en `requirements.txt` con el rango
  `>=8.0,<10`.

## 3. Arquitectura objetivo

```text
analog_finder/
  main.py
  PLAN.md
  AGENTS.md
  requirements.txt
  data/
    parametros.json   # categorías y parámetros del catálogo
    sitios.json
    destinos.json
    historial.json
  core/
    logic.py          # similitud y ranking (sin Flet)
    repository.py     # carga/guardado (sin Flet)
  ui/
    theme.py          # colores, tipografías, espaciados
    sidebar.py        # historial de búsquedas
    search_view.py    # destino + categorías + Buscar
    results_view.py   # ranking desplegable
    map_view.py       # mapamundi y marcadores
  tests/
```

Regla de dependencias:

```text
main.py -> ui/* -> core/*
core/* no importa flet ni ui/*
```

La UI no calcula similitudes. `core/logic.py` no dibuja controles. Los textos
de cada sitio salen de los datos, no de la vista.

## 4. Hitos

### Hito 1 — Esqueleto y tema (completado y aprobado)

- [x] Verificar versiones y API instalada de Flet / flet-map.
- [x] Crear estructura de carpetas y archivos base.
- [x] Crear `ui/theme.py` con paleta, tipografías y espaciados.
- [x] Crear `main.py` con ventana 1280x720, mínimo 1000x700 y tema oscuro M3.
- [x] Crear shell visual: barra lateral con estado vacío y área central.
- [x] Correr la app y verificar apertura, dimensiones y resize.
- [x] Esperar confirmación del usuario antes del hito 2.

Verificación realizada:

- La app abrió en escritorio con el título
  "Analog Finder - Análogos terrestres de Luna y Marte".
- Se capturó la ventana y se validó por OCR que los textos se renderizan en
  español, incluidos el historial vacío, el aviso de datos de ejemplo y el
  placeholder de búsqueda.
- Se detectó y corrigió un encabezado central con altura cero.
- Se probó la ventana en 1000x700: los textos se reacomodan, el contenido
  inferior queda accesible mediante scroll y la barra lateral no se rompe.
- Se verificó el scroll con la rueda del mouse en 1000x700: las tres tarjetas
  de pasos se alcanzan y se reacomodan sin desbordar.
- El shell se separó en `ui/sidebar.py` y `ui/search_view.py`; `main.py` quedó
  como punto de entrada y composición.
- La altura inicial se ajustó a 720 para no quedar debajo de la barra de tareas
  en una pantalla de 1366x768.
- Los logs de `flet run` no mostraron errores de runtime.

Criterio de aceptación: la app abre en escritorio, respeta el tamaño mínimo,
no desborda al redimensionar y todos los textos visibles están en español.

### Hito 2 — Pantalla de búsqueda con barra lateral (completado)

- [x] Selector grande Luna / Marte con estado seleccionado muy visible.
- [x] Acordeón de categorías con casillas por parámetro.
- [x] Botón Buscar deshabilitado hasta haber destino y al menos un parámetro.
- [x] Sidebar conectada al historial con estado vacío real.
- [x] Layout resistente a 1000x700 y a pantallas más grandes.
- [x] Correr app y mostrar resultado.

Verificación realizada:

- Se eligieron Luna y Marte con clic y el borde, el fondo y la marca de
  selección cambiaron en cada caso; el texto de ayuda nombró el destino activo.
- Se marcaron y desmarcaron parámetros: los contadores por categoría y el
  global ("1 de 3", "2 de 12") se actualizaron y el botón Buscar pasó de
  deshabilitado a habilitado y viceversa.
- Se abrió y cerró cada categoría del acordeón; solo una queda abierta y las
  categorías cerradas conservan sus parámetros marcados.
- Con una selección válida, Buscar mostró el SnackBar
  "Selección válida: Marte · 2 parámetros."; con selección incompleta el botón
  permanece deshabilitado.
- A 1280x720 entran las cuatro categorías y el pie fijo con Buscar.
- A 1000x700 la columna de parámetros exige un scroll corto; al desplazarla se
  alcanzan las cuatro categorías con sus subtítulos y el pie queda fijo. No hay
  desborde horizontal ni textos cortados de forma permanente.
- Las pruebas de clic se hicieron con la ventana en primer plano; los falsos
  positivos anteriores venían de clics enviados a la ventana de OpenCode.
- Los logs de `flet run` no mostraron errores de runtime.

Notas de implementación:

- La selección vive en `ui/search_view.py`; la vista solo entrega destino y
  parámetros al llamador. La vista no calcula el ranking.
- Al cierre del hito 2 el catálogo de categorías estaba dentro de la vista; el
  hito 3 lo reemplazó por `data/parametros.json` sin cambiar la interfaz.
- `ft.ExpansionTile` con `expanded=True` no se renderizaba de forma confiable en
  Flet 1.1.2, así que el acordeón se armó con encabezados y contenedores propios.
- Al cierre del hito 2 quedaba pendiente instalar pytest y probar similitud y
  ranking; se completó en el hito 3.

### Hito 3 — Lógica de ranking con tests (completado)

- [x] Definir contrato de datos (`es_ejemplo`, perfiles, parámetros, textos).
- [x] Crear `data/parametros.json`, `data/destinos.json` y `data/sitios.json`
      de ejemplo (12 sitios).
- [x] Implementar `cargar_sitios()` y `cargar_destinos()` en repository.
- [x] Implementar similitud `1 - |sitio - destino|` y promedio por parámetros.
- [x] Devolver puntaje total y puntaje por parámetro.
- [x] Tests de similitud, orden, parámetros vacíos y datos inválidos.
- [x] Ejecutar `python -m pytest`.

Verificación realizada:

- `python -m pytest -q`: 49 pruebas aprobadas, sin fallas.
- Prueba de integración con los datos reales y los 12 parámetros: Luna dio
  80 % para Isla Axel Heiberg e Isla Devon, y Marte dio 87 % para Isla Devon.
  El orden y los porcentajes coinciden con la fórmula acordada.
- Los tests cubren similitud por parámetro, simetría, promedio, orden del
  ranking, desempate por nombre, listas vacías y parámetros repetidos o
  faltantes.
- Los tests del repositorio cubren carga real del proyecto (4 categorías, 12
  parámetros, 2 destinos, 12 sitios), archivo ausente, JSON inválido, contenido
  que no es lista, ids repetidos, valores fuera de 0–1, parámetros faltantes o
  desconocidos, coordenadas fuera de rango y textos incompletos.
- Se corrigió una expectativa incorrecta del test de ranking: el último sitio
  promedia 0.75, no 0.625.
- La app se reinició y el catálogo de la pantalla de búsqueda ahora sale de
  `data/parametros.json`: se ven las cuatro categorías, los 12 parámetros y el
  contador "0 de 12 seleccionados".
- Se eligió Luna y Elevación: el botón Buscar se habilitó, el texto de ayuda
  mostró "Listo para comparar 1 parámetro con Luna." y el SnackBar confirmó
  "Selección válida: Luna · 1 parámetro.".
- A 1000x700 la pantalla mantiene el layout y el scroll corto ya conocido; no
  hay desborde horizontal.
- Los logs de `flet run` no mostraron errores de runtime.

Notas de implementación:

- `core/logic.py` no importa Flet y devuelve `ResultadoAnalogo` con el sitio,
  el puntaje por parámetro y el total.
- `core/repository.py` valida los archivos antes de entregarlos y falla con
  `ErrorDatos` y un mensaje concreto.
- La vista sólo mapea ids de categoría a iconos; no lee archivos ni calcula
  similitudes. `main.py` carga el catálogo y lo pasa a la vista.
- El ranking todavía no se muestra en pantalla: eso corresponde al hito 4.

### Hito 4 — Pantalla de resultados (completado)

- [x] Lista ordenada con nombre, país, porcentaje y barra.
- [x] Fila desplegable con barra por parámetro.
- [x] Textos de datos: qué es similar / dónde falla / para qué sirve.
- [x] Botón Ver mapa por resultado.
- [x] Estados: cargando, sin resultados, error.

Verificación realizada:

- Al presionar Buscar se pasa al ranking real: 12 sitios comparados con Luna
  y 3 parámetros, ordenados de mayor a menor.
- Los primeros puestos visibles fueron Svalbard 82 %, Desierto de Atacama
  80 %, Parque Nacional de Timanfaya 78 % e Isla Axel Heiberg 77 %.
- Se repitió la búsqueda con Marte y los mismos parámetros: el encabezado y el
  ranking cambiaron a Marte, con Dasht-e Lut 98 % y Mojave 95 % como primeros
  puestos.
- Cada tarjeta muestra nombre, país, porcentaje entero, barra de similitud y una
  flecha para desplegar el detalle.
- Al desplegar Svalbard se ven los tres textos traídos de `data/sitios.json`
  ("Qué es similar", "Dónde falla la analogía", "Para qué sirve en una misión")
  y las barras por parámetro: Elevación 70 %, Pendiente 95 % y Rugosidad del
  terreno 80 %.
- El botón "Ver mapa" existe en cada resultado; por ahora muestra el aviso
  "El mapa de Svalbard estará disponible en el hito 6." porque el mapa es el
  hito 6.
- "Volver a buscar" regresa a la pantalla de búsqueda conservando el destino y
  los parámetros elegidos.
- Los estados de carga, sin resultados y error se implementaron y se
  verificaron construyéndolos con los datos reales. El error muestra el mensaje
  real y una salida a la búsqueda.
- A 1280x720 se ven cuatro resultados completos y el resto queda en el scroll.
- A 1000x700 el encabezado y el aviso se reacomodan, no hay desborde horizontal
  y el scroll alcanza el detalle y las barras por parámetro.
- `python -m pytest -q` sigue pasando con 49 pruebas.
- Los logs de `flet run` no mostraron errores de runtime.

Notas de implementación:

- `ui/results_view.py` recibe `ResultadoAnalogo` ya calculados; no lee archivos
  ni recalcula similitudes. El porcentaje visible se redondea al entero.
- `main.py` alterna entre búsqueda y resultados y usa `page.run_task` para
  mostrar el estado de carga sin bloquear la interfaz.
- La barra lateral y el botón "Nueva búsqueda" siguen sin cambios: el historial
  persistente corresponde al hito 5.

### Hito 5 — Historial persistente (completado)

- [x] Guardar cada búsqueda en `data/historial.json` con fecha y categorías.
- [x] Reabrir un resultado desde la barra lateral.
- [x] Borrar una entrada.
- [x] Manejo de archivo ausente, vacío o corrupto.
- [x] Botón Nueva búsqueda.

Verificación realizada:

- Al buscar Luna con Elevación, Pendiente y Rugosidad, la búsqueda apareció en
  la barra lateral con el destino, la fecha local y "3 parámetros", y se creó
  `data/historial.json` con fecha ISO, parámetros y categorías derivadas.
- Una segunda búsqueda con Marte, dos parámetros de Topografía y Temperatura
  media quedó arriba de la anterior, con las categorías "Topografía · Clima".
- Al hacer clic en una entrada se reabre el ranking con su destino y sus
  parámetros, sin duplicar la búsqueda en el historial.
- El botón de borrar quita la entrada elegida y conserva las demás.
- "Nueva búsqueda" limpia destino, casillas, contador y categorías abiertas, y
  vuelve a dejar "Buscar análogos" deshabilitado.
- El historial sobrevive al reinicio de la app.
- Con el archivo ausente o vacío se muestra el estado vacío. Con un archivo
  corrupto se muestra el error real en la barra lateral, la búsqueda sigue
  funcionando y un intento de guardar informa el problema en un aviso.
- Se verificó a 1280x720 y a 1000x700, incluido abrir una entrada desde la
  barra lateral en el tamaño mínimo.
- `python -m pytest -q` pasa con **104 pruebas**.

Notas de implementación:

- `core/repository.py` expone `cargar_historial`, `guardar_busqueda` y
  `borrar_busqueda`; escribe de forma atómica, en UTF-8 y sin dependencias de
  Flet.
- `ui/sidebar.py` no lee archivos: recibe las entradas validadas y avisa al
  llamador cuando se abre, se borra o se pide una búsqueda nueva.
- `ui/search_view.py` ahora expone `VistaBusqueda`, con `reiniciar`, para que
  "Nueva búsqueda" limpie la selección sin duplicar estado.
- `main.py` guarda solo las búsquedas manuales exitosas; reabrir una entrada no
  la vuelve a guardar.

### Hito 6 — Mapa (completado)

- [x] Mapamundi con `flet-map` y tiles de OpenStreetMap.
- [x] Un marcador por sitio del ranking; al tocar muestra nombre y porcentaje.
- [x] Resaltar el sitio desde el cual se abrió el mapa.
- [x] Botón Volver a resultados.
- [x] Plan B si no hay internet o falla el tile provider.
- [x] Verificar clic de marcador y resize.

Verificación realizada:

- Al abrir el mapa desde un resultado se muestra el mapamundi con tiles de
  OpenStreetMap, atribución visible y un marcador por cada sitio del ranking.
- Los marcadores no se duplican: se limita el zoom mínimo a `1.2` para que el
  mundo no se repita en las ventanas de 1000 y 1280 px.
- Al tocar un marcador, la tarjeta inferior muestra el nombre del sitio, el
  país, las coordenadas y el porcentaje entero de similitud.
- El sitio desde el que se abrió el mapa queda resaltado con una estrella
  ámbar, el resto con marcadores cian y el seleccionado con el color de
  acento; la tarjeta muestra la placa "Origen del mapa".
- "Volver a resultados" restaura la pantalla de resultados y conserva la
  tarjeta expandida.
- A 1280x720 y a 1000x700 el mapa, la leyenda y la tarjeta se reacomodan
  sin desborde horizontal ni vertical.
- En el plan B, con el proveedor de tiles fuera de servicio, la app muestra
  el aviso "No pudimos cargar las imágenes del mapa..." y los marcadores
  siguen visibles sobre el fondo oscuro.
- `python -m pytest -q` pasa con **104 pruebas**.

Notas de implementación:

- `ui/map_view.py` recibe `ResultadoAnalogo` ya calculados; no lee archivos ni
  recalcula similitudes. El porcentaje visible se redondea al entero.
- `main.py` conserva la vista de resultados construida y la restaura al volver
  desde el mapa, y guarda el resultado actual para abrir el mapa con origen.
- El toque sobre el mapa selecciona el marcador más cercano dentro de un radio
  de 10°, porque `Marker.content` no siempre captura los gestos en Flet 1.1.2.
- La atribución visible usa `SimpleAttribution` con el texto de OpenStreetMap.

### Hito 7 — Pulido y README (completado)

- [x] Repasar estados vacío/cargando/sin resultados/error.
- [x] Contraste, tamaños mínimos de texto y espaciado en múltiplos de 8.
- [x] Aviso de datos de ejemplo visible en búsqueda y resultados.
- [x] README con instalación, ejecución, tests y límites de la analogía.
- [x] Revisión final de textos en español.
- [x] App y tests corriendo sin errores.

### Hito 8 — Conexión con la nube (en curso, primera parte completada)

El buscador pasa del modo de ejemplo al RPC `buscar_analogos_v2` de
Supabase. La similitud se calcula en la nube; el front solo dibuja.

- [x] Catálogo real: `data/parametros.json` con los 8 parámetros que la
      base produce (elevación, pendiente, rugosidad, temperatura media,
      amplitud día/noche, reflectancia, fracción diurna, energía solar),
      cada uno con `clave_db`, `unidad` y rango físico (`min`/`max`)
      tomado de `parametros_escalas`. Los ids de categoría coinciden con
      los del desglose del RPC (topografia, termico, superficie,
      iluminacion). Datos de ejemplo de sitios/destinos ajustados al
      nuevo catálogo (siguen con `es_ejemplo: true` para el modo local).
- [x] `core/nube.py`: cliente del RPC sin Flet. `cargar_credenciales`
      (lee `.env` de la raíz), `construir_perfil` (valores reales del
      usuario, pesos 1, la nube renormaliza), `buscar_analogos`,
      `datos_sitio` (fila cruda), extracción del sitio objetivo y de
      `tierra_top5`, y textos de resultado derivados del desglose (la
      vista no los inventa). Errores reales con `ErrorNube`.
- [x] `core/logic.py`: `ResultadoNube` (puntajes por categoría).
- [x] Pantalla de búsqueda: sliders de VALORES REALES con interruptor
      por parámetro (unidades visibles: m, °, K, fracción, W/m²). La
      selección viaja como {id_parametro: valor}.
- [x] Pantalla previa `ui/objetivo_view.py`: muestra el sitio de
      Luna/Marte que cumple la preferencia (nombre, tipo, coordenadas,
      similitud global + desglose por categoría, tabla de valores del
      sitio frente al objetivo pedido). Botón para continuar a los
      análogos. El mapa interactivo no aplica aquí (tiles solo Tierra).
- [x] `ui/results_view.py` y `ui/map_view.py`: soportan `ResultadoNube`
      (barras por categoría, subtítulo tipo/país, aviso configurable).
- [x] `main.py`: flujo nube → objetivo → resultados → mapa, con estados
      de carga, error (mensaje real) y sin resultados. Historial que
      guarda los valores reales elegidos (`entrada["valores"]`).
- [x] `python -m pytest -q`: 132 pruebas aprobadas (24 nuevas de nube,
      con HTTP simulado).
- [x] Robustez contra la DB real (sesión del 15/11): el RPC devuelve
      lat/lon como TEXTO (`d->>'lat'`) y filas con similitud NULL cuando
      ningún sitio registrado tiene los parámetros del perfil. El front
      normaliza números de texto, rechaza la fila sin dato con un
      mensaje honesto ("ningún sitio de Luna registrado tiene datos
      para estos parámetros") y ejecuta el HTTP en un hilo aparte con
      captura amplia de errores (antes, un TypeError mataba la tarea en
      silencio y la pantalla de carga quedaba colgada). Verificado en
      vivo: elevación −1000 → Tyndall (99.9 %, elevación real −1018 m)
      + 5 análogos terrestres.
- [ ] Verificación visual de la app en ejecución (pendiente del equipo).
- [ ] Probar contra la DB real: falta copiar el `.env` a la raíz del repo.
- [ ] `data/historial.json` viejo: entradas sin `valores` avisan y no se
      reabren con valores falsos.

Decisiones del hito:

- La similitud vive en la nube (RPC); `core/logic.py` queda para el modo
  local de ejemplo, hoy desconectado del flujo principal.
- El perfil objetivo lo construye el usuario con sliders en unidades
  físicas; no hay valores 0–1 en la pantalla de búsqueda.
- Los parámetros sin dato en la base (viento, composición, polvo,
  sismicidad, ángulo solar, visibilidad) salieron del catálogo.

## 5. Contrato de datos

`data/parametros.json` es la lista de categorías del catálogo:

```json
{
  "id": "topografia",
  "nombre": "Topografía",
  "descripcion": "Relieve, altura y forma del terreno.",
  "parametros": [
    {"id": "elevacion", "nombre": "Elevación"},
    {"id": "pendiente", "nombre": "Pendiente"}
  ]
}
```

`data/sitios.json` contiene los sitios terrestres:

```json
{
  "id": "atacama",
  "nombre": "Desierto de Atacama",
  "pais": "Chile",
  "lat": -23.5,
  "lon": -69.2,
  "es_ejemplo": true,
  "valores": {
    "elevacion": 0.85,
    "pendiente": 0.2
  },
  "textos": {
    "similar": "...",
    "falla": "...",
    "mision": "..."
  }
}
```

`data/destinos.json` contiene los perfiles de referencia:

```json
{
  "id": "luna",
  "nombre": "Luna",
  "zona": "Polo sur",
  "detalle": "Base permanente y recursos de hielo.",
  "es_ejemplo": true,
  "valores": {
    "elevacion": 0.75,
    "pendiente": 0.55
  }
}
```

`data/historial.json` guarda las búsquedas exitosas, de la más reciente a la
más vieja:

```json
[
  {
    "id": "11cec7c6609d444eaee34ef884e86428",
    "fecha": "2026-11-14T22:56:07",
    "destino_id": "luna",
    "destino_nombre": "Luna",
    "parametros": ["elevacion", "pendiente"],
    "categorias": ["Topografía"]
  }
]
```

- `fecha` usa ISO local; la barra lateral la muestra en formato breve.
- `parametros` no puede estar vacío y no admite ids repetidos.
- `categorias` se deriva de los parámetros al guardar, en el orden del catálogo.
- Un archivo ausente o vacío equivale a historial vacío; un archivo corrupto o
  con entradas inválidas se informa como `ErrorDatos` y no se sobrescribe.
- La escritura es atómica y en UTF-8. El archivo es dato local del usuario y
  está en `.gitignore`.

- Valores normalizados de 0 a 1.
- Las claves de `valores` deben coincidir exactamente con los ids de
  `data/parametros.json`; no se aceptan faltantes ni sobrantes.
- Los textos son contenido del dato, no de la vista. `similar`, `falla` y
  `mision` son obligatorios y no pueden estar vacíos.
- `es_ejemplo` debe ser `true` en todos los registros de esta etapa.
- Los ids son únicos dentro de cada archivo.

## 6. Dudas y decisiones pendientes

1. **Mapa sin internet (resuelto en hito 6):** se mantiene la dependencia de
   tiles remotos y se muestra un aviso visible; los marcadores siguen visibles
   sobre el fondo oscuro.
2. **Clic en marcador (resuelto en hito 6):** además de envolver el contenido,
   el mapa usa `on_tap` para seleccionar el marcador más cercano, porque el
   gesto del marcador no siempre se captura.
3. **Proveedor de tiles (resuelto en hito 6):** se usa OpenStreetMap estándar
   con atribución visible.
4. **Persistencia en app empaquetada:** `data/historial.json` funciona en
   desarrollo. Si se empaqueta, la carpeta de la app puede ser de solo lectura.
   ¿Mantenemos el JSON junto a la app o lo movemos a datos de usuario?
5. **Historial (resuelto en hito 5):** una búsqueda se guarda al presionar
   Buscar, solo si el ranking se calcula correctamente. Reabrir una entrada no
   la duplica.
6. **Categorías en el historial (resuelto en hito 5):** se muestran los nombres
   de categoría derivados de los parámetros; la fecha y la cantidad de
   parámetros acompañan la entrada.
7. **Empates:** propongo ordenar por porcentaje descendente y, en empate, por
   nombre del sitio.
8. **Redondeo:** el porcentaje visible se redondea al entero; el valor interno
   conserva decimales para ordenar.
9. **Carga:** el estado de carga será breve y explícito. No se simulará una
   espera larga; se usará el tiempo real del cálculo.
10. **Datos reales:** faltan definir fuentes y resolución espacial. La
    normalización 0–1 probablemente requiera documentar mínimos y máximos por
    parámetro.
11. **Alcance visual:** el hito 2 ya reemplazó el placeholder por el selector,
    el acordeón y el pie de acción. El ranking lógico está resuelto en el hito
    3; su pantalla y el mapa quedan para los hitos 4 y 6.

## 7. Comandos

Desde `analog_finder/`:

```powershell
python -m pip install -r requirements.txt
python -m pytest
flet run main.py
```

En esta terminal, si `flet` no está en PATH:

```powershell
& "$env:LOCALAPPDATA\Packages\PythonSoftwareFoundation.Python.3.13_qbz5n2kfra8p0\LocalCache\local-packages\Python313\Scripts\flet.exe" run main.py
```
