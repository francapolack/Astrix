# AGENTS.md — Reglas del proyecto Analog Finder

## Contexto

Proyecto para el NASA Space Apps Challenge 2026, challenge "Permanent Moon Base
Locations and Mars". La app busca sitios terrestres análogos a la Luna o Marte y
explica los límites de cada analogía.

## Reglas obligatorias

1. **Idioma:** todos los textos de interfaz, comentarios de código, nombres de
   dominio y documentación van en español. Los nombres de API de Flet se dejan
   como los define la librería.
2. **Encoding:** todos los archivos se guardan en UTF-8.
3. **Versión de Flet:** trabajar con la versión instalada, hoy Flet 1.1.2.
   Verificar `pip show flet` antes de cambiar APIs. En esta versión:
   - entrada con `ft.run(main)`;
   - botones con `ft.Button` / `ft.FilledButton`;
   - `ft.Dropdown` usa `on_select`;
   - barra de progreso con `ft.ProgressBar`;
   - tema Material 3 con `ft.Theme(use_material3=True, ...)`.
4. **Separación de capas:**
   - `ui/` no calcula puntajes ni lee archivos directamente.
   - `core/` no importa `flet` y no crea controles.
   - `main.py` solo configura la página y conecta vistas.
5. **Datos:** todo registro de ejemplo debe llevar `es_ejemplo: true`. La UI
   debe mostrar un aviso visible de que los datos son ilustrativos.
6. **Textos de resultados:** "Qué es similar", "Dónde falla la analogía" y
   "Para qué sirve en una misión" salen de campos del dato. No se inventan en
   la vista.
7. **No ocultar errores:** si algo falla, mostrar el error real en la consola o
   en la UI. No usar `except` mudos ni valores de relleno silenciosos.
8. **Sin funciones extra:** no agregar funcionalidades que no estén pedidas en
   el hito actual. Ante una duda, anotarla en `PLAN.md` y preguntar.
9. **Funciones cortas:** una responsabilidad por función, nombres claros,
   comentarios breves en español solo donde aporten.
10. **Diseño:** tema oscuro Material 3, estética espacial sobria, espaciados en
    múltiplos de 8, texto mínimo 14 px, contraste suficiente, ventana mínima
    1000x700 y layout que no se rompa al redimensionar.
11. **Estados:** toda vista debe contemplar vacío, cargando, sin resultados y
    error cuando corresponda.
12. **Tests:** la lógica de similitud y ranking se prueba con pytest antes de
    conectar la vista de resultados.

## Estructura y dependencias

```text
main.py -> ui/* -> core/*
core/* no importa flet ni ui/*
```

Archivos de datos:

```text
data/destinos.json    perfiles de referencia Luna / Marte
data/sitios.json      sitios terrestres candidatos
data/historial.json   búsquedas guardadas (se crea si no existe)
```

## Flujo de trabajo por hito

1. Trabajar solo el hito pedido.
2. Actualizar el estado del hito en `PLAN.md`.
3. Correr la app y los tests que existan.
4. Informar qué se verificó, qué falló y qué queda pendiente.
5. Frenar y esperar la palabra "seguí" antes del próximo hito.

## Comandos

```powershell
python -m pip install -r requirements.txt
python -m pytest
flet run main.py
```

Si `flet` no está en PATH en esta máquina:

```powershell
& "$env:LOCALAPPDATA\Packages\PythonSoftwareFoundation.Python.3.13_qbz5n2kfra8p0\LocalCache\local-packages\Python313\Scripts\flet.exe" run main.py
```

## Lo que no se debe hacer

- Presentar valores de ejemplo como datos científicos reales.
- Duplicar la fórmula de similitud en la UI.
- Hardcodear textos de resultados en las vistas.
- Cambiar la estructura de datos sin actualizar el repositorio y los tests.
- Avanzar de hito sin revisar la app en ejecución.
