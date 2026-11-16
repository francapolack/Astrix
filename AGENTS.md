# AGENTS.md — Producto Astrix (unificado)

Reglas para trabajar en este repositorio: el producto final que une el
colector de datos (NSAC) con la app de escritorio (Analog Finder) para el
retro NASA Space Apps 2026 *"Permanent Moon Base Locations and Mars"*.

## Reglas generales

1. **Idioma:** todo el código, docstrings, comentarios, textos de interfaz y
   documentación van en **español**. Los nombres de API de Flet/Supabase se
   dejan como los define la librería.
2. **Encoding:** archivos en **UTF-8**; en consola Windows usar
   `$env:PYTHONIOENCODING="utf-8"` (imprescindible para acentos).
3. **No inventar datos:** si una fuente no dio el dato, el campo queda NULL
   o con una `nota` honesta. Nunca rellenar silenciosamente. La UI muestra
   el estado real (vacío, cargando, sin resultados, error).
4. **No ocultar errores:** nada de `except` mudos; el error real se muestra
   en consola o en la UI.
5. **Sin funciones extra:** solo lo pedido por el hito actual; dudas a
   `PLAN.md` o a la conversación.

## Estructura y dependencias (una regla por capa)

```text
analog_finder/main.py -> analog_finder/ui/* -> analog_finder/core/*
analog_finder/core/*  no importa flet ni ui/*
analog_finder/ui/*    no calcula puntajes ni lee archivos directamente
colector_datos/*      no importa flet ni ui/*
nsac/*                solo hablar con APIs HTTP; nsac.http centraliza sesión
```

La **similitud y el ranking se calculan en la nube** (RPC `buscar_analogos_v2`
de `supabase/`): el front solo dibuja. `analog_finder/core/logic.py` queda
como respaldo offline si la nube falla.

## Archivos clave

- `supabase/esquema_rpc.sql` + `supabase/rpc_v2.sql` — esquema de la nube
  (idempotentes, se ejecutan en ese orden desde el SQL Editor).
- `colector_datos/NOTAS_NOCTURNAS.md` — bitácora: leerla antes de tocar el
  colector y añadir sección al final de cada sesión. Si los docs contradicen
  el código, gana el código (y se actualiza la nota).
- `colector_datos/README.md` — mapa parámetro→módulo→fuente.
- `analog_finder/PLAN.md` — contrato de datos del front y estado de hitos.

## Comandos

```powershell
# Setup (Windows, Python ≥ 3.10)
python -m venv .venv; .\.venv\Scripts\activate
pip install -r requirements.txt
$env:PYTHONIOENCODING="utf-8"

# App (desde analog_finder/)
flet run main.py

# Colector / nube (desde la raíz, donde está pyproject.toml)
python -m nsac.cli doctor                        # 14 fuentes en vivo, sin credenciales
python -m colector_datos.ejemplo_uso --rapido    # fumo del colector (sin GDS)
python -m colector_datos.poblador_supabase estado  # hilos de subida en vuelo
python -m colector_datos.poblador_supabase poblar  # subir catálogo (reanudable)
python -m colector_datos.carga_fondo             # tierra+luna+marte -> nube
python -m colector_datos.prueba_similitud_nube   # buscador v2 contra la DB

# Pruebas
python -m pytest
```

Módulos del colector se ejecutan como `python -m colector_datos.<modulo>`
**desde la raíz**, no desde dentro del paquete. Si `flet` no está en PATH:

```powershell
& "$env:LOCALAPPDATA\Packages\PythonSoftwareFoundation.Python.3.13_qbz5n2kfra8p0\LocalCache\local-packages\Python313\Scripts\flet.exe" run main.py
```

## Gotchas heredados (leídos a la dura)

- **Convenciones de bbox no homogéneas**: CMR/STAC `(oeste,sur,este,norte)`;
  ODE/GDS `(minlat,maxlat,oeste,este)`; ASF `(sur,oeste,norte,este)`. Usar
  `utilidades.cajas_gds` / `caja_stac`.
- **El GDS de PDS trabaja en longitudes 0-360**, es lento (minutos) y frágil;
  radio recortado a ±0.5°; si `ResultFiles` llega como string es error
  transitorio y la caché NO debe guardarlo.
- **CRS lunares/marcianas**: PROJ no las transforma (fórmulas manuales en
  `topografia_dtm.py`); tiles polares `stere` marcianos → error claro, sin
  dato.
- **Política DTM** (en `api.py`, no cambiar a la ligera): Luna ≥50 % píxeles
  válidos y ≥90 % cobertura (cae a GDS LOLA); Marte ≥50 % (sin respaldo).
- **Caché del colector** en `/data/` (gitignored, sin caducidad): sitio tibio
  ≈ 4-5 s vs 33-95 s frío. Ruta raíz con `NSAC_DATA_DIR`.
- **Flet 1.1.2** (verificada): `ft.run(main)`, `ft.Dropdown` usa `on_select`,
  `ft.ProgressBar`, tema M3 con `ft.Theme(use_material3=True, ...)`; ventana
  mínima 1000x700, layout que no se rompa al redimensionar.
- **`supabase` no entra al front**: la app consulta la API pública de la
  nube; la service key solo vive en el `.env` del poblador.

## Git

- Un fix no está hecho hasta que está **comiteado**.
- Este repo (`astrix`) es el producto final; los repos fuente son
  `frontend/` (francapolack/Astrix) y `backend/` (AxelRoda202/repo_improvisado,
  rama `supabase-candidatos`). Cambios de colector se discuten con el
  agente del backend antes de divergir.
