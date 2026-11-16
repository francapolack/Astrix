"""Barra lateral con el historial persistente de búsquedas.

La barra recibe las entradas ya validadas por ``core/repository.py``. No lee
archivos: avisa al llamador cuando se abre, se borra o se pide una búsqueda
nueva, y se repinta con ``refrescar`` después de cada cambio.
"""

from collections.abc import Callable
from datetime import datetime

import flet as ft

from ui.theme import (
    ANCHO_BARRA_LATERAL,
    COLORES,
    ESPACIO,
    RADIO,
    TEXTO,
)

MESES = (
    "ene",
    "feb",
    "mar",
    "abr",
    "may",
    "jun",
    "jul",
    "ago",
    "sep",
    "oct",
    "nov",
    "dic",
)

ICONOS_DESTINO = {
    "luna": (ft.Icons.NIGHTLIGHT_ROUND, COLORES["luna"], COLORES["luna_suave"]),
    "marte": (ft.Icons.PUBLIC, COLORES["marte"], COLORES["marte_suave"]),
}
ICONO_DESTINO_POR_DEFECTO = (
    ft.Icons.TRAVEL_EXPLORE,
    COLORES["acento"],
    COLORES["acento_suave"],
)


def _marca() -> ft.Row:
    """Logo y nombre de la app en la barra lateral."""
    return ft.Row(
        controls=[
            ft.Container(
                width=40,
                height=40,
                border_radius=RADIO["md"],
                bgcolor=COLORES["acento_suave"],
                alignment=ft.Alignment.CENTER,
                content=ft.Icon(
                    ft.Icons.TRAVEL_EXPLORE,
                    color=COLORES["acento"],
                    size=24,
                ),
            ),
            ft.Column(
                controls=[
                    ft.Text(
                        "Analog Finder",
                        size=TEXTO["subtitulo"],
                        weight=ft.FontWeight.W_700,
                        color=COLORES["texto"],
                    ),
                    ft.Text(
                        "Análogos planetarios",
                        size=TEXTO["cuerpo"],
                        color=COLORES["texto_tenue"],
                    ),
                ],
                spacing=0,
                expand=True,
            ),
        ],
        spacing=ESPACIO["sm"],
        vertical_alignment=ft.CrossAxisAlignment.CENTER,
    )


def _formatear_fecha(fecha_iso: str) -> str:
    """Convierte una fecha ISO en un texto breve para la barra lateral."""
    fecha = datetime.fromisoformat(fecha_iso)
    return f"{fecha.day} {MESES[fecha.month - 1]} {fecha.year} · {fecha:%H:%M}"


def _detalle_entrada(entrada: dict) -> str:
    """Fecha y cantidad de parámetros de una búsqueda guardada."""
    cantidad = len(entrada["parametros"])
    parametros = (
        "1 parámetro" if cantidad == 1 else f"{cantidad} parámetros"
    )
    return f"{_formatear_fecha(entrada['fecha'])} · {parametros}"


def _estado_vacio_historial() -> ft.Container:
    """Mensaje para cuando todavía no hay búsquedas guardadas."""
    return ft.Container(
        padding=ft.Padding.all(ESPACIO["md"]),
        bgcolor=COLORES["superficie_alterna"],
        border=ft.Border.all(1, COLORES["borde_suave"]),
        border_radius=RADIO["md"],
        content=ft.Column(
            controls=[
                ft.Icon(
                    ft.Icons.HISTORY,
                    color=COLORES["texto_tenue"],
                    size=32,
                ),
                ft.Text(
                    "Todavía no hay búsquedas",
                    size=TEXTO["cuerpo_grande"],
                    weight=ft.FontWeight.W_600,
                    color=COLORES["texto"],
                    text_align=ft.TextAlign.CENTER,
                ),
                ft.Text(
                    "Cuando busques un análogo, va a aparecer acá con su "
                    "destino y sus categorías.",
                    size=TEXTO["cuerpo"],
                    color=COLORES["texto_secundario"],
                    text_align=ft.TextAlign.CENTER,
                ),
            ],
            spacing=ESPACIO["xs"],
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
        ),
    )


def _estado_error_historial(mensaje: str) -> ft.Container:
    """Muestra el problema real que impide leer el historial."""
    return ft.Container(
        padding=ft.Padding.all(ESPACIO["md"]),
        bgcolor=COLORES["error_fondo"],
        border=ft.Border.all(1, COLORES["error"]),
        border_radius=RADIO["md"],
        content=ft.Column(
            controls=[
                ft.Icon(
                    ft.Icons.ERROR_OUTLINE,
                    color=COLORES["error"],
                    size=32,
                ),
                ft.Text(
                    "No se pudo leer el historial",
                    size=TEXTO["cuerpo_grande"],
                    weight=ft.FontWeight.W_600,
                    color=COLORES["texto"],
                    text_align=ft.TextAlign.CENTER,
                ),
                ft.Text(
                    mensaje,
                    size=TEXTO["cuerpo"],
                    color=COLORES["texto_secundario"],
                    text_align=ft.TextAlign.CENTER,
                ),
            ],
            spacing=ESPACIO["xs"],
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
        ),
    )


def _entrada_historial(
    entrada: dict,
    al_abrir: Callable[[dict], None] | None,
    al_borrar: Callable[[str], None] | None,
) -> ft.Container:
    """Tarjeta clickeable de una búsqueda guardada."""
    icono, color, fondo = ICONOS_DESTINO.get(
        entrada["destino_id"],
        ICONO_DESTINO_POR_DEFECTO,
    )
    boton_borrar = ft.IconButton(
        icon=ft.Icons.DELETE_OUTLINE,
        icon_color=COLORES["texto_tenue"],
        icon_size=18,
        width=32,
        height=32,
        tooltip="Borrar búsqueda",
        disabled=al_borrar is None,
        on_click=(
            None
            if al_borrar is None
            else lambda _, entrada_id=entrada["id"]: al_borrar(entrada_id)
        ),
        style=ft.ButtonStyle(
            padding=ft.Padding.all(ESPACIO["xs"] // 2),
            shape=ft.RoundedRectangleBorder(radius=RADIO["sm"]),
        ),
    )

    return ft.Container(
        padding=ft.Padding.all(ESPACIO["sm"]),
        bgcolor=COLORES["superficie_alterna"],
        border=ft.Border.all(1, COLORES["borde_suave"]),
        border_radius=RADIO["md"],
        ink=True,
        on_click=(
            None
            if al_abrir is None
            else lambda _: al_abrir(entrada)
        ),
        content=ft.Row(
            controls=[
                ft.Container(
                    width=32,
                    height=32,
                    border_radius=RADIO["sm"],
                    bgcolor=fondo,
                    alignment=ft.Alignment.CENTER,
                    content=ft.Icon(icono, color=color, size=18),
                ),
                ft.Column(
                    controls=[
                        ft.Text(
                            entrada["destino_nombre"],
                            size=TEXTO["cuerpo_grande"],
                            weight=ft.FontWeight.W_600,
                            color=COLORES["texto"],
                        ),
                        ft.Text(
                            _detalle_entrada(entrada),
                            size=TEXTO["cuerpo"],
                            color=COLORES["texto_secundario"],
                        ),
                        ft.Text(
                            " · ".join(entrada["categorias"]),
                            size=TEXTO["cuerpo"],
                            color=COLORES["texto_tenue"],
                            max_lines=2,
                            overflow=ft.TextOverflow.ELLIPSIS,
                        ),
                    ],
                    spacing=0,
                    expand=True,
                ),
                boton_borrar,
            ],
            spacing=ESPACIO["xs"],
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        ),
    )


class BarraLateral:
    """Historial visible, con acciones de abrir, borrar y empezar de nuevo."""

    def __init__(
        self,
        historial: list[dict] | None = None,
        al_abrir: Callable[[dict], None] | None = None,
        al_borrar: Callable[[str], None] | None = None,
        al_nueva: Callable[[], None] | None = None,
        error: str | None = None,
    ) -> None:
        self.historial = list(historial or [])
        self.al_abrir = al_abrir
        self.al_borrar = al_borrar
        self.al_nueva = al_nueva
        self.error = error

        self.contador = ft.Text(
            str(len(self.historial)),
            size=TEXTO["cuerpo"],
            color=COLORES["texto_tenue"],
        )
        self.zona = ft.Container(expand=True)
        self.boton_nueva = ft.OutlinedButton(
            content="Nueva búsqueda",
            icon=ft.Icons.ADD,
            width=ANCHO_BARRA_LATERAL - (ESPACIO["md"] * 2),
            disabled=al_nueva is None,
            on_click=(
                None if al_nueva is None else lambda _: self.al_nueva()
            ),
            style=ft.ButtonStyle(
                color=COLORES["texto"],
                side=ft.BorderSide(1, COLORES["borde"]),
                padding=ft.Padding.symmetric(
                    horizontal=ESPACIO["sm"],
                    vertical=ESPACIO["sm"],
                ),
                shape=ft.RoundedRectangleBorder(radius=RADIO["md"]),
            ),
        )
        self.raiz = self._construir()
        self._pintar_historial()

    def _construir(self) -> ft.Container:
        """Arma la estructura fija de la barra lateral."""
        return ft.Container(
            width=ANCHO_BARRA_LATERAL,
            bgcolor=COLORES["superficie"],
            border=ft.Border.only(
                right=ft.BorderSide(1, COLORES["borde"]),
            ),
            padding=ft.Padding.all(ESPACIO["md"]),
            content=ft.Column(
                controls=[
                    _marca(),
                    ft.Divider(
                        height=1,
                        thickness=1,
                        color=COLORES["borde_suave"],
                    ),
                    ft.Row(
                        controls=[
                            ft.Text(
                                "HISTORIAL",
                                size=TEXTO["cuerpo"],
                                weight=ft.FontWeight.W_600,
                                color=COLORES["texto_tenue"],
                            ),
                            ft.Container(expand=True),
                            self.contador,
                        ],
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    self.zona,
                    self.boton_nueva,
                ],
                spacing=ESPACIO["sm"],
                expand=True,
            ),
        )

    def refrescar(self, historial: list[dict], error: str | None = None) -> None:
        """Repinta la barra con una lista nueva y un error opcional."""
        self.historial = list(historial)
        self.error = error
        self._pintar_historial()

    def _pintar_historial(self) -> None:
        """Reemplaza el contenido de la zona de historial."""
        self.contador.value = str(len(self.historial))
        if self.error is not None:
            self.zona.alignment = ft.Alignment.CENTER
            self.zona.content = _estado_error_historial(self.error)
        elif not self.historial:
            self.zona.alignment = ft.Alignment.CENTER
            self.zona.content = _estado_vacio_historial()
        else:
            self.zona.alignment = ft.Alignment.TOP_LEFT
            self.zona.content = ft.Column(
                controls=[
                    _entrada_historial(entrada, self.al_abrir, self.al_borrar)
                    for entrada in self.historial
                ],
                spacing=ESPACIO["xs"],
                scroll=ft.ScrollMode.AUTO,
                expand=True,
            )
