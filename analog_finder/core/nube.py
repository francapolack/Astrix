"""Cliente del buscador de análogos en la nube (Supabase RPC v2).

Este módulo no importa Flet ni lee catálogos: construye el perfil a partir
de la selección de la vista, llama a los RPC del proyecto
(`supabase/esquema_rpc.sql` + `supabase/rpc_v2.sql`) y entrega los resultados
ya organizados. Los errores reales se comunican con `ErrorNube`, nunca se
ocultan.
"""

from __future__ import annotations

import json
from pathlib import Path

import requests

from core.logic import ResultadoNube

# Claves del RPC buscar_analogos_v2 por cuerpo elegido.
CLAVE_OBJETIVO = {"luna": "luna_top1", "marte": "marte_top1"}

RUTA_ENV = Path(__file__).resolve().parents[2] / ".env"


class ErrorNube(Exception):
    """Fallo al conectar o al consultar el buscador de la nube."""


# ---------------------------------------------------------------------------
# Credenciales
# ---------------------------------------------------------------------------

def _leer_env(ruta: Path) -> dict[str, str]:
    """Lee pares CLAVE=VALOR de un archivo .env simple."""
    valores: dict[str, str] = {}
    for linea in ruta.read_text(encoding="utf-8").splitlines():
        linea = linea.strip()
        if not linea or linea.startswith("#") or "=" not in linea:
            continue
        clave, valor = linea.split("=", 1)
        valores[clave.strip()] = valor.strip().strip('"').strip("'")
    return valores


def cargar_credenciales(ruta_env: Path | None = None) -> tuple[str, str]:
    """Devuelve (url, clave_api) del proyecto de Supabase.

    Prefiere SUPABASE_ANON_KEY (lectura pública); si no está, usa
    SUPABASE_KEY. El `.env` vive en la raíz del repo y nunca entra a git.
    """
    ruta = ruta_env or RUTA_ENV
    if not ruta.exists():
        raise ErrorNube(
            f"Falta el archivo .env en {ruta}: copia .env.example a .env y "
            "completa SUPABASE_URL y la clave de API."
        )
    valores = _leer_env(ruta)
    url = valores.get("SUPABASE_URL", "").rstrip("/")
    clave = valores.get("SUPABASE_ANON_KEY") or valores.get("SUPABASE_KEY")
    if not url.startswith("http"):
        raise ErrorNube(f"SUPABASE_URL no es una URL válida en {ruta}.")
    if not clave:
        raise ErrorNube(
            f"Falta SUPABASE_ANON_KEY o SUPABASE_KEY en {ruta}."
        )
    return url, clave


# ---------------------------------------------------------------------------
# Perfil a partir de la selección de la vista
# ---------------------------------------------------------------------------

def construir_perfil(categorias: list[dict], seleccion: dict) -> dict:
    """Convierte {id_parametro: valor} en el perfil JSONB del RPC.

    El perfil usa valores físicos reales (metros, grados, kelvin) con la
    clave de la base (`clave_db`). Cada parámetro elegido entra con peso 1:
    la función de la nube renormaliza los pesos.
    """
    if not isinstance(seleccion, dict) or not seleccion:
        raise ValueError("Hay que elegir al menos un parámetro con valor.")
    indice = {
        parametro["id"]: parametro
        for categoria in categorias
        for parametro in categoria["parametros"]
    }
    perfil: dict[str, dict[str, float]] = {}
    for parametro_id, valor in seleccion.items():
        parametro = indice.get(parametro_id)
        if parametro is None:
            raise ValueError(
                f"El catálogo no tiene el parámetro '{parametro_id}'."
            )
        if isinstance(valor, bool) or not isinstance(valor, (int, float)):
            raise ValueError(
                f"El valor de '{parametro_id}' debe ser un número."
            )
        minimo = parametro.get("min")
        maximo = parametro.get("max")
        if minimo is not None and valor < minimo or maximo is not None and valor > maximo:
            raise ValueError(
                f"El valor de '{parametro_id}' debe estar entre "
                f"{minimo} y {maximo}."
            )
        perfil[parametro["clave_db"]] = {
            "valor": float(valor),
            "peso": 1.0,
        }
    return perfil


# ---------------------------------------------------------------------------
# Llamadas al REST de Supabase
# ---------------------------------------------------------------------------

def _encabezados(clave: str) -> dict[str, str]:
    """Encabezados que PostgREST exige para llamar RPC o tablas."""
    return {
        "apikey": clave,
        "Authorization": f"Bearer {clave}",
        "Content-Type": "application/json",
    }


def buscar_analogos(url: str, clave: str, perfil: dict) -> dict:
    """Llama al RPC buscar_analogos_v2 con el perfil del usuario."""
    try:
        respuesta = requests.post(
            f"{url}/rest/v1/rpc/buscar_analogos_v2",
            headers=_encabezados(clave),
            json={"parametros": {"perfil": perfil}},
            timeout=30,
        )
    except requests.RequestException as error:
        raise ErrorNube(f"No se pudo conectar con la nube: {error}") from error
    if respuesta.status_code != 200:
        raise ErrorNube(
            "La nube respondió "
            f"{respuesta.status_code}: {respuesta.text[:300]}"
        )
    try:
        datos = respuesta.json()
    except ValueError as error:
        raise ErrorNube(
            f"La nube devolvió una respuesta que no es JSON: {error}"
        ) from error
    if not isinstance(datos, dict):
        raise ErrorNube("La respuesta de la nube no es un objeto.")
    return datos


def datos_sitio(url: str, clave: str, sitio_id: str) -> dict:
    """Trae la fila cruda de un sitio desde la tabla sitios_candidatos."""
    try:
        respuesta = requests.get(
            f"{url}/rest/v1/sitios_candidatos",
            params={"sitio_id": f"eq.{sitio_id}", "select": "*"},
            headers=_encabezados(clave),
            timeout=30,
        )
    except requests.RequestException as error:
        raise ErrorNube(f"No se pudo conectar con la nube: {error}") from error
    if respuesta.status_code != 200:
        raise ErrorNube(
            "La nube respondió "
            f"{respuesta.status_code}: {respuesta.text[:300]}"
        )
    filas = respuesta.json()
    if not isinstance(filas, list) or not filas:
        raise ErrorNube(f"El sitio '{sitio_id}' no está en la base.")
    return filas[0]


# ---------------------------------------------------------------------------
# Organización de la respuesta para las vistas
# ---------------------------------------------------------------------------

def extraer_sitio_objetivo(respuesta: dict, destino_id: str) -> dict:
    """Devuelve el sitio de Luna/Marte que encontró la nube."""
    clave = CLAVE_OBJETIVO.get(destino_id)
    if clave is None:
        raise ErrorNube(f"El destino '{destino_id}' no es luna ni marte.")
    objetivo = respuesta.get(clave)
    if not isinstance(objetivo, dict):
        raise ErrorNube(
            "La nube no devolvió ningún sitio de "
            f"{destino_id} para este perfil."
        )
    return objetivo


def extraer_analogos_tierra(respuesta: dict) -> list[dict]:
    """Devuelve la lista de análogos terrestres (puede estar vacía)."""
    analogos = respuesta.get("tierra_top5")
    if analogos is None:
        raise ErrorNube("La respuesta no incluye los análogos de la Tierra.")
    if not isinstance(analogos, list):
        raise ErrorNube("Los análogos de la Tierra no llegaron como lista.")
    return analogos


def textos_del_desglose(
    desglose: dict,
    categorias: list[dict],
    tipo: str | None,
) -> dict[str, str]:
    """Construye los tres textos de resultado a partir del desglose.

    Los textos salen de los datos (similitud por categoría y tipo del
    sitio); la vista no los inventa.
    """
    nombres = {
        categoria["id"]: categoria["nombre"] for categoria in categorias
    }
    con_dato = [
        (clave, float(valor))
        for clave, valor in desglose.items()
        if clave != "global" and isinstance(valor, (int, float))
    ]
    if not con_dato:
        raise ErrorNube(
            "El desglose no trae ninguna categoría con dato para comparar."
        )
    ordenadas = sorted(con_dato, key=lambda par: par[1], reverse=True)

    parecidas = ordenadas[:2]
    similar = "Se parece sobre todo en: " + ", ".join(
        f"{nombres.get(clave, clave)} ({round(valor * 100)} %)"
        for clave, valor in parecidas
    ) + "."

    bajas = [par for par in ordenadas if par[1] < 0.5]
    if bajas:
        falla = "La analogía falla en: " + ", ".join(
            f"{nombres.get(clave, clave)} ({round(valor * 100)} %)"
            for clave, valor in bajas
        ) + "."
    else:
        falla = (
            "Ninguna de las categorías elegidas baja del 50 %: la analogía "
            "es pareja; conviene mirar los valores crudos antes de decidir."
        )

    if tipo and str(tipo).strip():
        mision = f"Sitio de referencia del tipo '{tipo}'."
    else:
        mision = "El tipo de formación no figura en la base de datos."

    return {"similar": similar, "falla": falla, "mision": mision}


def _numero(valor) -> float | None:
    """Convierte a float lo que sea número real; lo demás queda None."""
    if isinstance(valor, bool) or not isinstance(valor, (int, float)):
        return None
    return float(valor)


def adaptar_sitio_nube(
    fila: dict,
    categorias: list[dict],
) -> "ResultadoNube":
    """Convierte una fila del RPC en un ResultadoNube listo para la vista.

    Los textos de resultado se generan aquí (a partir del desglose y del
    tipo del sitio) y viajan dentro de `sitio["textos"]`: la vista no los
    inventa.
    """
    desglose = fila.get("similitudes")
    if not isinstance(desglose, dict):
        raise ErrorNube(
            f"El resultado '{fila.get('sitio_id')}' no trae desglose."
        )
    total = _numero(desglose.get("global"))
    if total is None:
        raise ErrorNube(
            f"El resultado '{fila.get('sitio_id')}' no tiene similitud global."
        )
    puntajes = {
        clave: float(valor)
        for clave, valor in desglose.items()
        if isinstance(valor, (int, float))
    }
    sitio = {
        "id": fila.get("sitio_id"),
        "nombre": fila.get("nombre") or fila.get("sitio_id") or "Sin nombre",
        "tipo": fila.get("tipo") or "",
        "lat": _numero(fila.get("lat")),
        "lon": _numero(fila.get("lon")),
        "textos": textos_del_desglose(desglose, categorias, fila.get("tipo")),
        "es_ejemplo": False,
    }
    return ResultadoNube(sitio=sitio, puntajes=puntajes, total=total)
