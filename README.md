# ASTRIX

![ASTRIX Logo](logo.png)

Proyecto del equipo **BK2s** para el NASA Space Apps Challenge 2026, reto
*"Permanent Moon Base Locations and Mars"*.

Astrix encuentra **sitios terrestres análogos** a ubicaciones candidatas de
base en la **Luna** y **Marte**: dado un sitio candidato (lat, lon, radio),
el colector descarga datos reales de fuentes abiertas de NASA/ESA (LOLA,
Diviner, Kaguya, Copernicus DEM, Sentinel-2, NASA POWER...), los unifica en
un perfil comparado entre los tres cuerpos y busca en la nube (Supabase)
los análogos terrestres con mejores puntajes de similitud. La app de
escritorio muestra el ranking, el desglose por categoría (topografía,
clima/geología, iluminación) y el mapa.

## Estructura del repositorio

```text
analog_finder/      App de escritorio (Flet 1.1.2). Vistas y estado.
  core/             Similitud y acceso a datos (sin Flet)
  ui/               Vistas: búsqueda, resultados, mapa, barra lateral
  data/             Catálogo de parámetros, destinos y sitios
  tests/            Pruebas con pytest
nsac/               Capa de acceso a fuentes HTTP (PDS, USGS, Copernicus...)
colector_datos/     El producto de datos: obtener_datos_sitio() + nube
supabase/           Esquema y RPC del buscador en la nube (SQL)
examples/           Ejemplos de uso del colector
```

## Instalación (Windows, Python ≥ 3.10)

```powershell
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
$env:PYTHONIOENCODING="utf-8"   # acentos en la consola de Windows
```

Credenciales: copiar `.env.example` a `.env` y completar `SUPABASE_URL` y
`SUPABASE_KEY` (la clave de servicio solo hace falta para poblar la nube;
el front consulta la API pública). Las demás credenciales son opcionales
y solo para descargas.

## Ejecución

```powershell
# La app (desde analog_finder/)
flet run main.py

# Verificación del colector (desde la raíz)
python -m nsac.cli doctor                          # fuentes en vivo
python -m colector_datos.ejemplo_uso --rapido      # fumo del colector
python -m colector_datos.poblador_supabase estado  # estado de la nube
python -m colector_datos.prueba_similitud_nube     # buscador v2 contra la DB

# Pruebas
python -m pytest
```

## Cómo funciona

1. `obtener_datos_sitio(cuerpo, lat, lon, radio)` devuelve un diccionario
   con secciones fijas (`metadatos / topografia / termico / superficie /
   iluminacion`) y **las mismas claves en Luna, Marte y Tierra**.
2. El poblador sube esos resúmenes a la tabla `sitios_candidatos` de
   Supabase (reanudable, con guardián de almacenamiento del plan Free).
3. El buscador (RPC `buscar_analogos_v2`) normaliza con los rangos de
   `parametros_escalas`, pondera con el perfil elegido por el usuario y
   devuelve `luna_top1 + marte_top1 + tierra_top5` con desglose por
   categoría.
4. La app muestra el ranking, los textos por sitio y el mapa. Los valores
   que una fuente no dio quedan NULL: **nunca se inventan números**.

## Créditos — equipo BK2s

**Alma Tolosa** (@TolosaAlma) · **Facundo Roda** (@AxelRoda202) ·
**Franca Polack** (@francapolack) · **Matias Gil** (@escudero819) ·
**Romina Arias** (@AriasRominaFlorencia) · **Sofia Grillo** (@sofigrillo16-lec)
