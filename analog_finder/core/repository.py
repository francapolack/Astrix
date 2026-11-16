"""Carga y validación de los datos de Analog Finder.

La interfaz no lee archivos: pide los datos a este módulo. Los datos actuales
son de ejemplo y así queda declarado en cada registro con ``es_ejemplo``.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from uuid import uuid4

RUTA_DATOS = Path(__file__).resolve().parent.parent / "data"

ARCHIVO_PARAMETROS = "parametros.json"
ARCHIVO_DESTINOS = "destinos.json"
ARCHIVO_SITIOS = "sitios.json"
ARCHIVO_HISTORIAL = "historial.json"

CAMPOS_CATEGORIA = ("id", "nombre", "descripcion", "parametros")
CAMPOS_DESTINO = ("id", "nombre", "zona", "detalle", "es_ejemplo", "valores")
CAMPOS_HISTORIAL = (
    "id",
    "fecha",
    "destino_id",
    "destino_nombre",
    "parametros",
    "categorias",
)
CAMPOS_SITIO = (
    "id",
    "nombre",
    "pais",
    "lat",
    "lon",
    "es_ejemplo",
    "valores",
    "textos",
)
CAMPOS_TEXTO = ("similar", "falla", "mision")


class ErrorDatos(Exception):
    """Problema de lectura o de validación de los archivos de datos."""


def cargar_categorias(ruta_datos: Path | None = None) -> list[dict]:
    """Devuelve las categorías y sus parámetros, validados."""
    ruta = _resolver_ruta(ruta_datos)
    categorias = _leer_lista(ARCHIVO_PARAMETROS, ruta)
    _validar_categorias(categorias, ruta / ARCHIVO_PARAMETROS)
    return categorias


def cargar_destinos(ruta_datos: Path | None = None) -> list[dict]:
    """Devuelve los perfiles de referencia Luna y Marte, validados."""
    ruta = _resolver_ruta(ruta_datos)
    ids_parametros = _ids_parametros(cargar_categorias(ruta))
    destinos = _leer_lista(ARCHIVO_DESTINOS, ruta)
    _validar_registros(destinos, CAMPOS_DESTINO, ruta / ARCHIVO_DESTINOS)
    _validar_ids_unicos(destinos, ruta / ARCHIVO_DESTINOS)
    for indice, destino in enumerate(destinos):
        _validar_valores(
            destino,
            ids_parametros,
            ruta / ARCHIVO_DESTINOS,
            indice,
        )
    return destinos


def cargar_sitios(ruta_datos: Path | None = None) -> list[dict]:
    """Devuelve los sitios terrestres candidatos, validados."""
    ruta = _resolver_ruta(ruta_datos)
    ids_parametros = _ids_parametros(cargar_categorias(ruta))
    sitios = _leer_lista(ARCHIVO_SITIOS, ruta)
    _validar_registros(sitios, CAMPOS_SITIO, ruta / ARCHIVO_SITIOS)
    _validar_ids_unicos(sitios, ruta / ARCHIVO_SITIOS)
    for indice, sitio in enumerate(sitios):
        _validar_coordenadas(sitio, ruta / ARCHIVO_SITIOS, indice)
        _validar_textos(sitio, ruta / ARCHIVO_SITIOS, indice)
        _validar_valores(sitio, ids_parametros, ruta / ARCHIVO_SITIOS, indice)
    return sitios


def cargar_historial(ruta_datos: Path | None = None) -> list[dict]:
    """Devuelve las búsquedas guardadas, de la más reciente a la más vieja.

    Un archivo ausente o vacío significa historial vacío. Un archivo corrupto
    o con entradas inválidas se informa como ``ErrorDatos`` para no perder
    datos en silencio.
    """
    ruta = _resolver_ruta(ruta_datos) / ARCHIVO_HISTORIAL
    if not ruta.exists():
        return []
    try:
        texto = ruta.read_text(encoding="utf-8")
    except OSError as error:
        raise ErrorDatos(
            f"No se pudo leer el historial {ruta}: {error}"
        ) from error
    if not texto.strip():
        return []

    try:
        contenido = json.loads(texto)
    except json.JSONDecodeError as error:
        raise ErrorDatos(
            f"El archivo {ruta} no es un JSON válido: {error}"
        ) from error
    if not isinstance(contenido, list):
        raise ErrorDatos(f"El archivo {ruta} debe contener una lista.")
    _validar_historial(contenido, ruta)
    return _normalizar_historial(contenido)


def guardar_busqueda(
    destino: dict,
    pesos: dict,
    categorias: list[dict],
    ruta_datos: Path | None = None,
    valores: dict | None = None,
) -> dict:
    """Agrega una búsqueda al historial y devuelve la entrada creada.

    La entrada guarda el nombre del destino, los parámetros activos, sus
    pesos y las categorías derivadas, para que la barra lateral y los
    resultados no dependan del catálogo. En el modo nube, `valores`
    guarda el valor real (metros, grados, kelvin) elegido por el usuario
    para cada parámetro, para poder reabrir la búsqueda tal cual.
    """
    if not isinstance(destino, dict):
        raise ValueError("El destino de la búsqueda debe ser un objeto.")
    destino_id = destino.get("id")
    destino_nombre = destino.get("nombre")
    if not isinstance(destino_id, str) or not destino_id.strip():
        raise ValueError("El destino de la búsqueda necesita un id válido.")
    if not isinstance(destino_nombre, str) or not destino_nombre.strip():
        raise ValueError("El destino de la búsqueda necesita un nombre válido.")

    activos = _pesos_activos_historial(pesos)
    parametros = list(activos)
    nombres_categorias = _categorias_de_parametros(parametros, categorias)
    valores_reales: dict[str, float] | None = None
    if valores is not None:
        if not isinstance(valores, dict) or not valores:
            raise ValueError("Los valores de la búsqueda deben ser un objeto.")
        valores_reales = {}
        for parametro, valor in valores.items():
            if not isinstance(parametro, str) or not parametro.strip():
                raise ValueError(
                    "El id del parámetro debe ser un texto no vacío."
                )
            if isinstance(valor, bool) or not isinstance(valor, (int, float)):
                raise ValueError(
                    f"El valor de '{parametro}' debe ser un número."
                )
            valores_reales[parametro] = float(valor)
        if set(valores_reales) != set(parametros):
            raise ValueError(
                "Los valores no coinciden con los parámetros de la búsqueda."
            )
    entrada = {
        "id": uuid4().hex,
        "fecha": datetime.now().isoformat(timespec="seconds"),
        "destino_id": destino_id,
        "destino_nombre": destino_nombre,
        "parametros": parametros,
        "pesos": {parametro: int(peso) for parametro, peso in activos.items()},
        "categorias": nombres_categorias,
    }
    if valores_reales is not None:
        entrada["valores"] = valores_reales

    historial = cargar_historial(ruta_datos)
    historial.insert(0, entrada)
    _escribir_historial(historial, ruta_datos)
    return entrada


def borrar_busqueda(
    entrada_id: str,
    ruta_datos: Path | None = None,
) -> list[dict]:
    """Elimina una entrada del historial y devuelve la lista restante."""
    historial = cargar_historial(ruta_datos)
    restante = [entrada for entrada in historial if entrada["id"] != entrada_id]
    if len(restante) == len(historial):
        ruta = _resolver_ruta(ruta_datos) / ARCHIVO_HISTORIAL
        raise ErrorDatos(
            f"No se encontró la búsqueda '{entrada_id}' en {ruta}."
        )
    _escribir_historial(restante, ruta_datos)
    return restante


def _categorias_de_parametros(
    parametros: list[str],
    categorias: list[dict],
) -> list[str]:
    """Deriva los nombres de categoría, en el orden del catálogo."""
    if not isinstance(parametros, list) or not parametros:
        raise ValueError("La búsqueda necesita al menos un parámetro.")
    if any(not isinstance(item, str) or not item.strip() for item in parametros):
        raise ValueError("Los parámetros deben ser ids no vacíos.")
    if len(set(parametros)) != len(parametros):
        raise ValueError("La búsqueda tiene parámetros repetidos.")

    seleccionados = set(parametros)
    conocidos = {
        parametro["id"]
        for categoria in categorias
        for parametro in categoria["parametros"]
    }
    desconocidos = seleccionados - conocidos
    if desconocidos:
        raise ValueError(
            "El catálogo no tiene los parámetros: "
            f"{', '.join(sorted(desconocidos))}."
        )

    return [
        categoria["nombre"]
        for categoria in categorias
        if any(
            parametro["id"] in seleccionados
            for parametro in categoria["parametros"]
        )
    ]


def _pesos_activos_historial(pesos) -> dict[str, int]:
    """Valida y normaliza los pesos de una búsqueda para el historial."""
    if not isinstance(pesos, dict) or not pesos:
        raise ValueError("La búsqueda necesita al menos un parámetro.")
    activos: dict[str, int] = {}
    for parametro, peso in pesos.items():
        if not isinstance(parametro, str) or not parametro.strip():
            raise ValueError("El id del parámetro debe ser un texto no vacío.")
        if isinstance(peso, bool) or not isinstance(peso, (int, float)):
            raise ValueError("El peso debe ser un número.")
        peso_entero = int(peso)
        if peso < 0 or peso > 10 or peso_entero < 1:
            raise ValueError("El peso debe estar entre 1 y 10.")
        activos[parametro] = peso_entero
    if not activos:
        raise ValueError("La búsqueda necesita al menos un parámetro activo.")
    return activos


def _normalizar_historial(historial: list[dict]) -> list[dict]:
    """Convierte entradas viejas (solo lista) a pesos, con peso 5 por defecto."""
    normalizado: list[dict] = []
    for entrada in historial:
        entrada = dict(entrada)
        parametros = entrada.get("parametros", [])
        if isinstance(parametros, dict):
            if "pesos" not in entrada:
                entrada["pesos"] = dict(parametros)
            parametros = list(parametros)
        if not isinstance(parametros, list):
            parametros = []
        parametros = [str(item) for item in parametros]

        pesos = entrada.get("pesos")
        if not isinstance(pesos, dict):
            pesos = {parametro: 5 for parametro in parametros}
        else:
            pesos = dict(pesos)
            for parametro in parametros:
                if parametro not in pesos:
                    pesos[parametro] = 5
        pesos = {
            str(parametro): int(peso) if not isinstance(peso, bool) and isinstance(peso, (int, float)) else 5
            for parametro, peso in pesos.items()
        }
        # Asegura que los pesos correspondan a parámetros conocidos.
        pesos = {parametro: peso for parametro, peso in pesos.items() if parametro in parametros or parametro in pesos}
        entrada["parametros"] = parametros
        entrada["pesos"] = pesos
        normalizado.append(entrada)
    return normalizado


def _validar_historial(historial: list, ruta: Path) -> None:
    """Valida las entradas guardadas antes de mostrarlas o ampliarlas."""
    _validar_registros(historial, CAMPOS_HISTORIAL, ruta)
    _validar_ids_unicos(historial, ruta)

    for indice, entrada in enumerate(historial):
        numero = indice + 1
        if not entrada["id"].strip():
            raise ErrorDatos(f"Hay un id inválido en {ruta}.")
        for campo in ("destino_id", "destino_nombre"):
            valor = entrada[campo]
            if not isinstance(valor, str) or not valor.strip():
                raise ErrorDatos(
                    f"El campo '{campo}' de la búsqueda {numero} de {ruta} "
                    f"no puede estar vacío."
                )
        _validar_fecha(entrada["fecha"], numero, ruta)
        _validar_lista_textos(entrada["parametros"], "parametros", numero, ruta)
        _validar_lista_textos(entrada["categorias"], "categorias", numero, ruta)
        pesos = entrada.get("pesos")
        if pesos is not None:
            if not isinstance(pesos, dict):
                raise ErrorDatos(
                    f"El campo 'pesos' de la búsqueda {numero} de {ruta} "
                    f"debe ser un objeto."
                )
            for clave, valor in pesos.items():
                if not isinstance(clave, str) or not clave.strip():
                    raise ErrorDatos(
                        f"El campo 'pesos' de la búsqueda {numero} de {ruta} "
                        f"tiene una clave inválida."
                    )
                if isinstance(valor, bool) or not isinstance(valor, (int, float)):
                    raise ErrorDatos(
                        f"El peso de '{clave}' en la búsqueda {numero} de "
                        f"{ruta} debe ser un número."
                    )
        if len(set(entrada["parametros"])) != len(entrada["parametros"]):
            raise ErrorDatos(
                f"La búsqueda {numero} de {ruta} tiene parámetros repetidos."
            )


def _validar_fecha(fecha: str, numero: int, ruta: Path) -> None:
    """Exige una fecha ISO que la barra lateral pueda formatear."""
    try:
        datetime.fromisoformat(fecha)
    except (TypeError, ValueError) as error:
        raise ErrorDatos(
            f"La fecha de la búsqueda {numero} de {ruta} no es ISO válida."
        ) from error


def _validar_lista_textos(
    valor,
    campo: str,
    numero: int,
    ruta: Path,
) -> None:
    """Exige una lista no vacía de textos no vacíos."""
    if not isinstance(valor, list) or not valor:
        raise ErrorDatos(
            f"El campo '{campo}' de la búsqueda {numero} de {ruta} debe ser "
            f"una lista con al menos un elemento."
        )
    for item in valor:
        if not isinstance(item, str) or not item.strip():
            raise ErrorDatos(
                f"El campo '{campo}' de la búsqueda {numero} de {ruta} tiene "
                f"un valor vacío."
            )


def _escribir_historial(historial: list[dict], ruta_datos: Path | None) -> None:
    """Escribe el historial completo de forma atómica y en UTF-8."""
    ruta = _resolver_ruta(ruta_datos) / ARCHIVO_HISTORIAL
    temporal = ruta.with_name(f"{ruta.name}.tmp")
    try:
        ruta.parent.mkdir(parents=True, exist_ok=True)
        temporal.write_text(
            json.dumps(historial, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        temporal.replace(ruta)
    except OSError as error:
        raise ErrorDatos(
            f"No se pudo guardar el historial en {ruta}: {error}"
        ) from error


def _resolver_ruta(ruta_datos: Path | None) -> Path:
    """Usa la carpeta de datos indicada o la del proyecto."""
    return Path(ruta_datos) if ruta_datos is not None else RUTA_DATOS


def _leer_lista(nombre: str, ruta_datos: Path) -> list:
    """Lee una lista JSON y falla con un mensaje claro si no se puede."""
    ruta = ruta_datos / nombre
    if not ruta.exists():
        raise ErrorDatos(f"No se encontró el archivo de datos: {ruta}")
    try:
        contenido = json.loads(ruta.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise ErrorDatos(
            f"El archivo {ruta} no es un JSON válido: {error}"
        ) from error
    if not isinstance(contenido, list):
        raise ErrorDatos(f"El archivo {ruta} debe contener una lista.")
    if not contenido:
        raise ErrorDatos(f"El archivo {ruta} no tiene registros.")
    return contenido


def _ids_parametros(categorias: list[dict]) -> set[str]:
    """Reúne los ids de todos los parámetros del catálogo."""
    return {
        parametro["id"]
        for categoria in categorias
        for parametro in categoria["parametros"]
    }


def _validar_categorias(categorias: list, ruta: Path) -> None:
    """Valida la estructura del catálogo de categorías y parámetros."""
    _validar_registros(categorias, CAMPOS_CATEGORIA, ruta)
    _validar_ids_unicos(categorias, ruta)

    ids_parametros: set[str] = set()
    for indice, categoria in enumerate(categorias):
        parametros = categoria["parametros"]
        if not isinstance(parametros, list) or not parametros:
            raise ErrorDatos(
                f"La categoría '{categoria['id']}' de {ruta} no tiene "
                f"parámetros."
            )
        for parametro in parametros:
            if not isinstance(parametro, dict):
                raise ErrorDatos(
                    f"El parámetro {parametro!r} de la categoría "
                    f"'{categoria['id']}' en {ruta} no es un objeto."
                )
            for campo in ("id", "nombre"):
                if campo not in parametro:
                    raise ErrorDatos(
                        f"Falta el campo '{campo}' en un parámetro de la "
                        f"categoría '{categoria['id']}' en {ruta}."
                    )
            identificador = parametro["id"]
            if identificador in ids_parametros:
                raise ErrorDatos(
                    f"El parámetro '{identificador}' está repetido en {ruta}."
                )
            ids_parametros.add(identificador)


def _validar_registros(
    registros: list,
    campos: tuple[str, ...],
    ruta: Path,
) -> None:
    """Comprueba que cada registro sea un objeto con los campos pedidos."""
    for indice, registro in enumerate(registros):
        if not isinstance(registro, dict):
            raise ErrorDatos(
                f"El registro {indice + 1} de {ruta} no es un objeto."
            )
        for campo in campos:
            if campo not in registro:
                raise ErrorDatos(
                    f"Falta el campo '{campo}' en el registro "
                    f"{indice + 1} de {ruta}."
                )
        if "es_ejemplo" in campos and not isinstance(
            registro["es_ejemplo"],
            bool,
        ):
            raise ErrorDatos(
                f"El campo 'es_ejemplo' del registro {indice + 1} de {ruta} "
                f"debe ser verdadero o falso."
            )


def _validar_ids_unicos(registros: list[dict], ruta: Path) -> None:
    """Evita ids repetidos, que romperían el ranking y el historial."""
    vistos: set[str] = set()
    for registro in registros:
        identificador = registro["id"]
        if not isinstance(identificador, str) or not identificador:
            raise ErrorDatos(f"Hay un id inválido en {ruta}.")
        if identificador in vistos:
            raise ErrorDatos(
                f"El id '{identificador}' está repetido en {ruta}."
            )
        vistos.add(identificador)


def _validar_valores(
    registro: dict,
    ids_parametros: set[str],
    ruta: Path,
    indice: int,
) -> None:
    """Exige un valor normalizado por cada parámetro del catálogo."""
    valores = registro["valores"]
    numero_registro = indice + 1
    if not isinstance(valores, dict):
        raise ErrorDatos(
            f"El campo 'valores' del registro {numero_registro} de {ruta} "
            f"debe ser un objeto."
        )

    faltantes = ids_parametros - set(valores)
    if faltantes:
        raise ErrorDatos(
            f"Al registro {numero_registro} de {ruta} le faltan valores para: "
            f"{', '.join(sorted(faltantes))}."
        )
    sobrantes = set(valores) - ids_parametros
    if sobrantes:
        raise ErrorDatos(
            f"El registro {numero_registro} de {ruta} tiene parámetros "
            f"desconocidos: {', '.join(sorted(sobrantes))}."
        )

    for parametro, valor in valores.items():
        if isinstance(valor, bool) or not isinstance(valor, (int, float)):
            raise ErrorDatos(
                f"El valor de '{parametro}' en el registro {numero_registro} "
                f"de {ruta} debe ser un número."
            )
        if not 0.0 <= valor <= 1.0:
            raise ErrorDatos(
                f"El valor de '{parametro}' en el registro {numero_registro} "
                f"de {ruta} debe estar entre 0 y 1."
            )


def _validar_coordenadas(sitio: dict, ruta: Path, indice: int) -> None:
    """Comprueba que latitud y longitud estén en rango."""
    numero_registro = indice + 1
    lat = sitio["lat"]
    lon = sitio["lon"]
    if isinstance(lat, bool) or not isinstance(lat, (int, float)):
        raise ErrorDatos(
            f"La latitud del registro {numero_registro} de {ruta} debe ser "
            f"un número."
        )
    if isinstance(lon, bool) or not isinstance(lon, (int, float)):
        raise ErrorDatos(
            f"La longitud del registro {numero_registro} de {ruta} debe ser "
            f"un número."
        )
    if not -90.0 <= lat <= 90.0:
        raise ErrorDatos(
            f"La latitud del registro {numero_registro} de {ruta} está fuera "
            f"de rango."
        )
    if not -180.0 <= lon <= 180.0:
        raise ErrorDatos(
            f"La longitud del registro {numero_registro} de {ruta} está fuera "
            f"de rango."
        )


def _validar_textos(sitio: dict, ruta: Path, indice: int) -> None:
    """Exige los tres textos que la pantalla de resultados va a mostrar."""
    textos = sitio["textos"]
    numero_registro = indice + 1
    if not isinstance(textos, dict):
        raise ErrorDatos(
            f"El campo 'textos' del registro {numero_registro} de {ruta} debe "
            f"ser un objeto."
        )
    for campo in CAMPOS_TEXTO:
        if not isinstance(textos.get(campo), str) or not textos[campo].strip():
            raise ErrorDatos(
                f"Falta el texto '{campo}' en el registro {numero_registro} "
                f"de {ruta}."
            )
