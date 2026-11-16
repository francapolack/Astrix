"""Pantalla previa: el sitio de Luna o Marte que encontró el buscador.

Antes de mostrar los análogos terrestres, esta vista presenta el lugar del
planeta objetivo que cumple la preferencia del usuario: su nombre, tipo,
coordenadas, similitud con la preferencia y sus valores reales para los
parámetros elegidos. La vista no calcula nada: recibe los datos ya listos.
"""

from collections.abc import Callable

import flet as ft

from core.nube import CAMPOS_DATOS, campos_de_datos
from ui.theme import COLORES, ESPACIO, RADIO, TEXTO


def _formatear_valor(valor: float | None, unidad: str) -> str:
    """Texto del valor crudo con su unidad; None es honesto: sin dato."""
    if valor is None:
        return "sin dato en esta consulta"
    if unidad == "fracción":
        return f"{valor:.2f} frac."
    return f"{valor:g} {unidad}".strip()


def _aviso_datos(texto: str) -> ft.Container:
    """Aviso visible sobre el origen de los datos."""
    return ft.Container(
        padding=ft.Padding.symmetric(
            horizontal=ESPACIO["sm"],
            vertical=ESPACIO["xs"],
        ),
        bgcolor=COLORES["aviso_fondo"],
        border=ft.Border.all(1, COLORES["aviso_borde"]),
        border_radius=RADIO["md"],
        content=ft.Row(
            controls=[
                ft.Icon(
                    ft.Icons.SCIENCE,
                    color=COLORES["aviso"],
                    size=20,
                ),
                ft.Text(
                    texto,
                    size=TEXTO["cuerpo"],
                    color=COLORES["texto_secundario"],
                    expand=True,
                ),
            ],
            spacing=ESPACIO["xs"],
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        ),
    )


def _coordenadas(lat: float | None, lon: float | None) -> str:
    """Texto de coordenadas en grados; sin dato se dice claro."""
    if lat is None or lon is None:
        return "Coordenadas: sin dato en esta consulta."
    lat_hemisferio = "N" if lat >= 0 else "S"
    lon_hemisferio = "E" if lon >= 0 else "O"
    return (
        f"Coordenadas: {abs(lat):.2f}° {lat_hemisferio}, "
        f"{abs(lon):.2f}° {lon_hemisferio}"
    )


def _barra_categoria(nombre: str, puntaje: float) -> ft.Column:
    """Etiqueta, porcentaje y barra de similitud de una categoría."""
    return ft.Column(
        controls=[
            ft.Row(
                controls=[
                    ft.Text(
                        nombre,
                        size=TEXTO["cuerpo"],
                        color=COLORES["texto"],
                        expand=True,
                    ),
                    ft.Text(
                        f"{round(puntaje * 100)} %",
                        size=TEXTO["cuerpo"],
                        color=COLORES["texto_secundario"],
                    ),
                ],
                spacing=ESPACIO["xs"],
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            ft.ProgressBar(
                value=max(0.0, min(1.0, puntaje)),
                bar_height=6,
                color=COLORES["acento"],
                bgcolor=COLORES["superficie_alta"],
                border_radius=RADIO["sm"],
            ),
        ],
        spacing=ESPACIO["xs"],
    )


def _fila_campo(
    nombre: str,
    valor_sitio: float | None,
    unidad: str,
    valor_objetivo: float | None = None,
) -> ft.Row:
    """Una fila de la tabla de los 9 campos: sitio vs. objetivo pedido."""
    detalle = _formatear_valor(valor_sitio, unidad)
    if valor_objetivo is not None:
        detalle += "  (objetivo: " + _formatear_valor(
            valor_objetivo, unidad
        ) + ")"
    return ft.Row(
        controls=[
            ft.Text(
                nombre,
                size=TEXTO["cuerpo"],
                color=COLORES["texto"],
                width=180,
            ),
            ft.Text(
                detalle,
                size=TEXTO["cuerpo"],
                weight=ft.FontWeight.W_600,
                color=(
                    COLORES["texto"]
                    if valor_sitio is not None
                    else COLORES["aviso"]
                ),
                expand=True,
            ),
        ],
        spacing=ESPACIO["sm"],
        vertical_alignment=ft.CrossAxisAlignment.CENTER,
    )


def _tarjeta_sitio(objetivo: dict) -> ft.Container:
    """Tarjeta principal con los datos del sitio objetivo."""
    tipo = objetivo.get("tipo")
    subtitulo = tipo if tipo and str(tipo).strip() else "Sitio del catálogo"
    return ft.Container(
        padding=ft.Padding.all(ESPACIO["md"]),
        bgcolor=COLORES["superficie_alterna"],
        border=ft.Border.all(2, COLORES["acento"]),
        border_radius=RADIO["lg"],
        content=ft.Column(
            controls=[
                ft.Text(
                    objetivo.get("nombre") or "Sitio sin nombre",
                    size=TEXTO["titulo"],
                    weight=ft.FontWeight.W_700,
                    color=COLORES["texto"],
                ),
                ft.Text(
                    subtitulo,
                    size=TEXTO["cuerpo"],
                    color=COLORES["texto_secundario"],
                ),
                ft.Text(
                    _coordenadas(objetivo.get("lat"), objetivo.get("lon")),
                    size=TEXTO["cuerpo"],
                    color=COLORES["texto_tenue"],
                ),
            ],
            spacing=ESPACIO["xs"],
        ),
    )


def construir_vista_objetivo(
    objetivo: dict,
    datos: dict,
    destino: dict,
    categorias: list[dict],
    seleccion: dict[str, float],
    aviso: str,
    al_volver: Callable[[], None] | None = None,
    al_continuar: Callable[[], None] | None = None,
) -> ft.Container:
    """Devuelve la pantalla del sitio objetivo lista para montar.

    `objetivo` es el resultado del RPC (nombre, tipo, lat, lon,
    similitudes); `datos` es la fila cruda del sitio con sus valores
    reales; `seleccion` son los valores objetivo que pidió el usuario.
    """
    desglose = objetivo.get("similitudes")
    if not isinstance(desglose, dict):
        raise ValueError(
            "El sitio objetivo no trae el desglose de similitud."
        )
    total = desglose.get("global")
    if not isinstance(total, (int, float)):
        raise ValueError(
            "El sitio objetivo no tiene similitud global con la preferencia."
        )

    indice = {
        parametro["id"]: parametro
        for categoria in categorias
        for parametro in categoria["parametros"]
    }

    barras: list[ft.Control] = []
    for categoria in categorias:
        puntaje = desglose.get(categoria["id"])
        if isinstance(puntaje, (int, float)):
            barras.append(_barra_categoria(categoria["nombre"], float(puntaje)))

    # La tabla SIEMPRE muestra los 9 campos del contrato; en los que el
    # usuario pidió, se agrega entre paréntesis el objetivo elegido.
    campos = campos_de_datos(datos)
    unidades = {clave: unidad for clave, _n, unidad in CAMPOS_DATOS}
    objetivos_por_clave = {
        indice[parametro_id]["clave_db"]: float(valor)
        for parametro_id, valor in seleccion.items()
        if parametro_id in indice
    }
    filas_campos: list[ft.Control] = [
        _fila_campo(
            nombre,
            campos.get(clave_db),
            unidades.get(clave_db, ""),
            objetivos_por_clave.get(clave_db),
        )
        for clave_db, nombre, _unidad in CAMPOS_DATOS
    ]

    contenido = ft.Column(
        controls=[
            _tarjeta_sitio(objetivo),
            ft.Column(
                controls=[
                    ft.Text(
                        "Similitud con tu preferencia",
                        size=TEXTO["cuerpo_grande"],
                        weight=ft.FontWeight.W_600,
                        color=COLORES["texto"],
                    ),
                    ft.ProgressBar(
                        value=max(0.0, min(1.0, float(total))),
                        bar_height=8,
                        color=COLORES["acento"],
                        bgcolor=COLORES["superficie_alta"],
                        border_radius=RADIO["sm"],
                    ),
                    ft.Text(
                        f"{round(float(total) * 100)} %",
                        size=TEXTO["cuerpo"],
                        color=COLORES["texto_secundario"],
                    ),
                    *barras,
                ],
                spacing=ESPACIO["xs"],
            ),
            ft.Container(
                padding=ft.Padding.all(ESPACIO["sm"]),
                bgcolor=COLORES["superficie_alterna"],
                border=ft.Border.all(1, COLORES["borde_suave"]),
                border_radius=RADIO["md"],
                content=ft.Column(
                    controls=[
                        ft.Text(
                            "Datos del sitio (los 9 campos del catálogo)",
                            size=TEXTO["cuerpo_grande"],
                            weight=ft.FontWeight.W_600,
                            color=COLORES["texto"],
                        ),
                        *filas_campos,
                        ft.Text(
                            "Los análogos terrestres se buscan con TODOS "
                            "los campos con valor de este sitio, no solo "
                            "con los que pediste.",
                            size=TEXTO["cuerpo"],
                            color=COLORES["texto_tenue"],
                        ),
                        ft.Text(
                            "El mapa interactivo solo cubre la Tierra "
                            "(los tiles son de OpenStreetMap).",
                            size=TEXTO["cuerpo"],
                            color=COLORES["texto_tenue"],
                        ),
                    ],
                    spacing=ESPACIO["xs"],
                ),
            ),
        ],
        spacing=ESPACIO["md"],
        scroll=ft.ScrollMode.AUTO,
        expand=True,
    )

    botonera = ft.Container(
        padding=ft.Padding.only(top=ESPACIO["sm"]),
        border=ft.Border.only(
            top=ft.BorderSide(1, COLORES["borde_suave"]),
        ),
        content=ft.Row(
            controls=[
                ft.Container(expand=True),
                ft.OutlinedButton(
                    content="Volver a buscar",
                    icon=ft.Icons.ARROW_BACK,
                    on_click=lambda _: al_volver() if al_volver else None,
                    style=ft.ButtonStyle(
                        color=COLORES["texto"],
                        side=ft.BorderSide(1, COLORES["borde"]),
                        padding=ft.Padding.symmetric(
                            horizontal=ESPACIO["sm"],
                            vertical=ESPACIO["xs"],
                        ),
                        shape=ft.RoundedRectangleBorder(radius=RADIO["md"]),
                    ),
                ),
                ft.FilledButton(
                    content="Buscar análogos en la Tierra",
                    icon=ft.Icons.TRAVEL_EXPLORE,
                    on_click=lambda _: (
                        al_continuar() if al_continuar else None
                    ),
                    style=ft.ButtonStyle(
                        bgcolor=COLORES["acento"],
                        color=COLORES["fondo"],
                        elevation=0,
                        padding=ft.Padding.symmetric(
                            horizontal=ESPACIO["md"],
                        ),
                        shape=ft.RoundedRectangleBorder(radius=RADIO["md"]),
                        text_style=ft.TextStyle(
                            size=TEXTO["cuerpo"],
                            weight=ft.FontWeight.W_700,
                        ),
                    ),
                ),
            ],
            spacing=ESPACIO["sm"],
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        ),
    )

    return ft.Container(
        expand=True,
        bgcolor=COLORES["fondo"],
        padding=ft.Padding.all(ESPACIO["lg"]),
        content=ft.Column(
            controls=[
                ft.Text(
                    "El lugar de referencia",
                    size=TEXTO["titulo"],
                    weight=ft.FontWeight.W_700,
                    color=COLORES["texto"],
                ),
                ft.Text(
                    "El sitio de "
                    f"{destino.get('nombre', destino.get('id', ''))} que "
                    "mejor cumple tu preferencia. Revisalo antes de ver "
                    "sus análogos terrestres.",
                    size=TEXTO["cuerpo"],
                    color=COLORES["texto_tenue"],
                ),
                _aviso_datos(aviso),
                contenido,
                botonera,
            ],
            spacing=ESPACIO["xs"],
            expand=True,
        ),
    )
