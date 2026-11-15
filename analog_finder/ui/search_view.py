"""Pantalla de búsqueda: destino, parámetros y acción principal.

La vista maneja la selección visual, pero no calcula similitudes. Cuando la
selección es válida entrega el destino y los ids de los parámetros al llamador.
"""

from collections.abc import Callable

import flet as ft

from ui.theme import COLORES, ESPACIO, RADIO, TEXTO

# Los iconos son decisión visual de la interfaz, no un dato del catálogo.
ICONOS_CATEGORIA = {
    "topografia": ft.Icons.TERRAIN,
    "clima": ft.Icons.THERMOSTAT,
    "geologia": ft.Icons.GRAIN,
    "iluminacion": ft.Icons.WB_SUNNY,
}
ICONO_CATEGORIA_POR_DEFECTO = ft.Icons.CATEGORY

DESTINOS = (
    {
        "id": "luna",
        "nombre": "Luna",
        "zona": "Polo sur",
        "detalle": "Base permanente y recursos de hielo.",
        "icono": ft.Icons.NIGHTLIGHT_ROUND,
        "color": COLORES["luna"],
        "fondo": COLORES["luna_suave"],
    },
    {
        "id": "marte",
        "nombre": "Marte",
        "zona": "Jezero",
        "detalle": "Aterrizaje y exploración de superficie.",
        "icono": ft.Icons.PUBLIC,
        "color": COLORES["marte"],
        "fondo": COLORES["marte_suave"],
    },
)


def _encabezado() -> ft.Container:
    """Encabezado fijo de la pantalla con aviso de datos de ejemplo."""
    return ft.Container(
        height=56,
        content=ft.Row(
            controls=[
                ft.Column(
                    controls=[
                        ft.Text(
                            "Nueva búsqueda",
                            size=TEXTO["titulo"],
                            weight=ft.FontWeight.W_700,
                            color=COLORES["texto"],
                        ),
                        ft.Text(
                            "Elegí el destino y los parámetros para comparar.",
                            size=TEXTO["cuerpo"],
                            color=COLORES["texto_tenue"],
                        ),
                    ],
                    spacing=0,
                    expand=True,
                ),
                ft.Container(
                    padding=ft.Padding.symmetric(
                        horizontal=ESPACIO["sm"],
                        vertical=ESPACIO["xs"],
                    ),
                    bgcolor=COLORES["aviso_fondo"],
                    border=ft.Border.all(1, COLORES["aviso_borde"]),
                    border_radius=RADIO["sm"],
                    content=ft.Row(
                        controls=[
                            ft.Icon(
                                ft.Icons.INFO_OUTLINE,
                                color=COLORES["aviso"],
                                size=16,
                            ),
                            ft.Text(
                                "Datos de ejemplo",
                                size=TEXTO["cuerpo"],
                                weight=ft.FontWeight.W_600,
                                color=COLORES["aviso"],
                            ),
                        ],
                        spacing=ESPACIO["xs"],
                        tight=True,
                    ),
                ),
            ],
            spacing=ESPACIO["sm"],
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        ),
    )


def _aviso_datos() -> ft.Container:
    """Aviso visible sobre el carácter ilustrativo de los datos."""
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
                    "Datos de ejemplo: los perfiles, las coordenadas y los "
                    "puntajes de esta versión son ilustrativos.",
                    size=TEXTO["cuerpo"],
                    color=COLORES["texto_secundario"],
                    expand=True,
                ),
            ],
            spacing=ESPACIO["xs"],
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        ),
    )


def _titulo_seccion(titulo: str, detalle: ft.Control) -> ft.Row:
    """Encabezado de una sección con un detalle alineado a la derecha."""
    return ft.Row(
        controls=[
            ft.Text(
                titulo,
                size=TEXTO["cuerpo"],
                weight=ft.FontWeight.W_700,
                color=COLORES["acento"],
            ),
            ft.Container(expand=True),
            detalle,
        ],
        spacing=ESPACIO["sm"],
        vertical_alignment=ft.CrossAxisAlignment.CENTER,
    )


class VistaBusqueda:
    """Estado y controles de la pantalla de búsqueda."""

    def __init__(
        self,
        categorias: list[dict],
        al_buscar: Callable[[str, dict[str, int]], None] | None = None,
    ) -> None:
        if not categorias:
            raise ValueError(
                "La pantalla de búsqueda necesita al menos una categoría."
            )
        self.categorias = categorias
        self.total_parametros = sum(
            len(categoria["parametros"]) for categoria in categorias
        )
        self.al_buscar = al_buscar
        self.destino: str | None = None
        self.pesos: dict[str, int] = {
            parametro["id"]: 0
            for categoria in categorias
            for parametro in categoria["parametros"]
        }
        self.tarjetas: dict[str, ft.Container] = {}
        self.marcas: dict[str, ft.Icon] = {}
        self.deslizadores: dict[str, ft.Slider] = {}
        self.etiquetas_peso: dict[str, ft.Text] = {}
        self.subtitulos: dict[str, ft.Text] = {}
        self.cuerpos: dict[str, ft.Container] = {}
        self.flechas: dict[str, ft.Icon] = {}
        self.categorias_abiertas: set[str] = {categorias[0]["id"]}

        self.contador_parametros = ft.Text(
            f"0 de {self.total_parametros} activos",
            size=TEXTO["cuerpo"],
            color=COLORES["texto_tenue"],
        )
        self.ayuda_boton = ft.Text(
            "Elegí un destino y al menos un parámetro para buscar.",
            size=TEXTO["cuerpo"],
            color=COLORES["texto_secundario"],
            expand=True,
        )
        self.boton = self._crear_boton()
        self.raiz = self._construir()

    def _construir(self) -> ft.Container:
        """Compone encabezado, columnas de trabajo y pie de acción."""
        columnas = ft.Row(
            controls=[
                ft.Container(
                    width=304,
                    content=self._seccion_destino(),
                ),
                ft.Container(
                    expand=True,
                    content=self._seccion_parametros(),
                ),
            ],
            spacing=ESPACIO["md"],
            vertical_alignment=ft.CrossAxisAlignment.START,
        )
        contenido = ft.Column(
            controls=[columnas],
            scroll=ft.ScrollMode.AUTO,
            expand=True,
        )

        return ft.Container(
            expand=True,
            bgcolor=COLORES["fondo"],
            padding=ft.Padding.all(ESPACIO["lg"]),
            content=ft.Column(
                controls=[
                    _encabezado(),
                    _aviso_datos(),
                    contenido,
                    self._pie_accion(),
                ],
                spacing=ESPACIO["xs"],
                expand=True,
            ),
        )

    def _seccion_destino(self) -> ft.Column:
        """Selector grande con los dos perfiles de referencia."""
        return ft.Column(
            controls=[
                _titulo_seccion(
                    "DESTINO",
                    ft.Text(
                        "Un perfil de referencia",
                        size=TEXTO["cuerpo"],
                        color=COLORES["texto_tenue"],
                    ),
                ),
                ft.Column(
                    controls=[
                        self._crear_tarjeta_destino(destino)
                        for destino in DESTINOS
                    ],
                    spacing=ESPACIO["xs"],
                ),
            ],
            spacing=ESPACIO["xs"],
        )

    def _crear_tarjeta_destino(self, destino: dict) -> ft.Container:
        """Tarjeta clickeable de un destino, con marca de selección."""
        marca = ft.Icon(
            ft.Icons.CHECK_CIRCLE,
            color=destino["color"],
            size=24,
            visible=False,
        )
        tarjeta = ft.Container(
            padding=ft.Padding.all(ESPACIO["sm"]),
            bgcolor=COLORES["superficie_alterna"],
            border=ft.Border.all(2, COLORES["borde"]),
            border_radius=RADIO["lg"],
            ink=True,
            on_click=lambda _, destino_id=destino["id"]: self._elegir_destino(
                destino_id
            ),
            content=ft.Column(
                controls=[
                    ft.Row(
                        controls=[
                            ft.Container(
                                width=48,
                                height=48,
                                border_radius=RADIO["md"],
                                bgcolor=COLORES["superficie_alta"],
                                alignment=ft.Alignment.CENTER,
                                content=ft.Icon(
                                    destino["icono"],
                                    color=destino["color"],
                                    size=28,
                                ),
                            ),
                            ft.Column(
                                controls=[
                                    ft.Text(
                                        destino["nombre"],
                                        size=TEXTO["subtitulo"],
                                        weight=ft.FontWeight.W_700,
                                        color=COLORES["texto"],
                                    ),
                                    ft.Text(
                                        destino["zona"],
                                        size=TEXTO["cuerpo"],
                                        color=destino["color"],
                                    ),
                                ],
                                spacing=0,
                                expand=True,
                            ),
                            marca,
                        ],
                        spacing=ESPACIO["sm"],
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    ft.Text(
                        destino["detalle"],
                        size=TEXTO["cuerpo"],
                        color=COLORES["texto_secundario"],
                    ),
                ],
                spacing=ESPACIO["xs"],
            ),
        )
        self.tarjetas[destino["id"]] = tarjeta
        self.marcas[destino["id"]] = marca
        return tarjeta

    def _seccion_parametros(self) -> ft.Column:
        """Acordeón de categorías con una casilla por parámetro."""
        return ft.Column(
            controls=[
                _titulo_seccion("PARÁMETROS", self.contador_parametros),
                ft.Column(
                    controls=[
                        self._crear_categoria(categoria)
                        for categoria in self.categorias
                    ],
                    spacing=ESPACIO["xs"],
                ),
            ],
            spacing=ESPACIO["xs"],
        )

    def _crear_categoria(self, categoria: dict) -> ft.Container:
        """Una categoría del acordeón con encabezado clickeable."""
        abierta = categoria["id"] in self.categorias_abiertas
        subtitulo = ft.Text(
            self._texto_categoria(categoria, 0),
            size=TEXTO["cuerpo"],
            color=COLORES["texto_tenue"],
        )
        self.subtitulos[categoria["id"]] = subtitulo

        flecha = ft.Icon(
            ft.Icons.EXPAND_LESS if abierta else ft.Icons.EXPAND_MORE,
            color=COLORES["texto_secundario"],
            size=24,
        )
        self.flechas[categoria["id"]] = flecha

        cuerpo = ft.Container(
            visible=abierta,
            padding=ft.Padding.only(
                left=ESPACIO["sm"],
                right=ESPACIO["sm"],
                bottom=ESPACIO["xs"],
            ),
            content=ft.Column(
                controls=[
                    self._crear_slider(parametro)
                    for parametro in categoria["parametros"]
                ],
                spacing=0,
            ),
        )
        self.cuerpos[categoria["id"]] = cuerpo

        encabezado = ft.Container(
            padding=ft.Padding.symmetric(
                horizontal=ESPACIO["sm"],
                vertical=ESPACIO["xs"],
            ),
            ink=True,
            tooltip=categoria["descripcion"],
            on_click=lambda _, categoria_id=categoria["id"]: (
                self._alternar_categoria(categoria_id)
            ),
            content=ft.Row(
                controls=[
                    ft.Icon(
                        ICONOS_CATEGORIA.get(
                            categoria["id"],
                            ICONO_CATEGORIA_POR_DEFECTO,
                        ),
                        color=COLORES["acento"],
                        size=24,
                    ),
                    ft.Column(
                        controls=[
                            ft.Text(
                                categoria["nombre"],
                                size=TEXTO["cuerpo_grande"],
                                weight=ft.FontWeight.W_600,
                                color=COLORES["texto"],
                            ),
                            subtitulo,
                        ],
                        spacing=0,
                        expand=True,
                    ),
                    flecha,
                ],
                spacing=ESPACIO["sm"],
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
        )

        return ft.Container(
            bgcolor=COLORES["superficie_alterna"],
            border=ft.Border.all(1, COLORES["borde_suave"]),
            border_radius=RADIO["md"],
            clip_behavior=ft.ClipBehavior.ANTI_ALIAS,
            content=ft.Column(
                controls=[encabezado, cuerpo],
                spacing=0,
            ),
        )

    def _alternar_categoria(self, categoria_id: str) -> None:
        """Abre una categoría y cierra la anterior."""
        if categoria_id in self.categorias_abiertas:
            self.categorias_abiertas.clear()
        else:
            self.categorias_abiertas = {categoria_id}

        self._aplicar_categorias_abiertas()
        self.raiz.update()

    def _aplicar_categorias_abiertas(self) -> None:
        """Sincroniza el cuerpo y la flecha de cada categoría."""
        for identificador, cuerpo in self.cuerpos.items():
            abierta = identificador in self.categorias_abiertas
            cuerpo.visible = abierta
            self.flechas[identificador].icon = (
                ft.Icons.EXPAND_LESS if abierta else ft.Icons.EXPAND_MORE
            )

    def _crear_slider(self, parametro: dict) -> ft.Row:
        """Slider de importancia de un parámetro, identificado por su id."""
        parametro_id = parametro["id"]
        etiqueta = ft.Text(
            "No usado",
            size=TEXTO["cuerpo"],
            color=COLORES["texto_tenue"],
            width=40,
            text_align=ft.TextAlign.RIGHT,
        )
        self.etiquetas_peso[parametro_id] = etiqueta

        deslizador = ft.Slider(
            min=0,
            max=10,
            divisions=10,
            value=0,
            data=parametro_id,
            active_color=COLORES["acento"],
            inactive_color=COLORES["superficie_alta"],
            thumb_color=COLORES["acento_fuerte"],
            on_change=self._cambiar_peso,
            width=260,
        )
        self.deslizadores[parametro_id] = deslizador

        return ft.Row(
            controls=[
                ft.Text(
                    parametro["nombre"],
                    size=TEXTO["cuerpo"],
                    color=COLORES["texto"],
                    width=160,
                ),
                deslizador,
                etiqueta,
            ],
            spacing=ESPACIO["xs"],
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )

    def _pie_accion(self) -> ft.Container:
        """Pie fijo con la ayuda y el botón principal."""
        return ft.Container(
            padding=ft.Padding.only(top=ESPACIO["sm"]),
            border=ft.Border.only(
                top=ft.BorderSide(1, COLORES["borde_suave"]),
            ),
            content=ft.Row(
                controls=[
                    ft.Row(
                        controls=[
                            ft.Icon(
                                ft.Icons.INFO_OUTLINE,
                                color=COLORES["texto_tenue"],
                                size=20,
                            ),
                            self.ayuda_boton,
                        ],
                        spacing=ESPACIO["xs"],
                        expand=True,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    self.boton,
                ],
                spacing=ESPACIO["sm"],
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
        )

    def _crear_boton(self) -> ft.FilledButton:
        """Botón principal, deshabilitado hasta tener una selección válida."""
        return ft.FilledButton(
            content="Buscar análogos",
            icon=ft.Icons.SEARCH,
            icon_color=COLORES["fondo"],
            width=232,
            height=48,
            disabled=True,
            on_click=self._buscar,
            style=ft.ButtonStyle(
                bgcolor=COLORES["acento"],
                color=COLORES["fondo"],
                elevation=0,
                padding=ft.Padding.symmetric(horizontal=ESPACIO["md"]),
                shape=ft.RoundedRectangleBorder(radius=RADIO["md"]),
                text_style=ft.TextStyle(
                    size=TEXTO["cuerpo"],
                    weight=ft.FontWeight.W_700,
                ),
            ),
        )

    def _elegir_destino(self, destino_id: str) -> None:
        """Actualiza el destino y repinta las tarjetas."""
        self.destino = destino_id
        self._pintar_destinos()
        self._refrescar_estado()
        self.raiz.update()

    def _pintar_destinos(self) -> None:
        """Marca visualmente la tarjeta del destino elegido."""
        for destino in DESTINOS:
            elegido = destino["id"] == self.destino
            tarjeta = self.tarjetas[destino["id"]]
            tarjeta.bgcolor = (
                destino["fondo"] if elegido else COLORES["superficie_alterna"]
            )
            tarjeta.border = ft.Border.all(
                2,
                destino["color"] if elegido else COLORES["borde"],
            )
            self.marcas[destino["id"]].visible = elegido

    def _cambiar_peso(self, evento: ft.Event[ft.Slider]) -> None:
        """Actualiza el peso de un parámetro según el slider."""
        parametro_id = evento.control.data
        valor = int(round(evento.control.value or 0))
        self.pesos[parametro_id] = valor
        etiqueta = self.etiquetas_peso[parametro_id]
        if valor == 0:
            etiqueta.value = "No usado"
            etiqueta.color = COLORES["texto_tenue"]
        else:
            etiqueta.value = str(valor)
            etiqueta.color = COLORES["acento"]

        self._actualizar_subtitulos()
        self._refrescar_estado()
        etiqueta.update()
        self.raiz.update()

    def reiniciar(self) -> None:
        """Limpia la selección y deja la pantalla como al inicio."""
        self.destino = None
        for parametro_id in self.pesos:
            self.pesos[parametro_id] = 0
            self.deslizadores[parametro_id].value = 0
            self.etiquetas_peso[parametro_id].value = "No usado"
            self.etiquetas_peso[parametro_id].color = COLORES["texto_tenue"]
        self._pintar_destinos()
        self.categorias_abiertas = {self.categorias[0]["id"]}
        self._aplicar_categorias_abiertas()
        self._actualizar_subtitulos()
        self._refrescar_estado()

    def _actualizar_subtitulos(self) -> None:
        """Muestra cuántos parámetros están activos en cada categoría."""
        for categoria in self.categorias:
            activos = sum(
                1
                for parametro in categoria["parametros"]
                if self.pesos.get(parametro["id"], 0) > 0
            )
            self.subtitulos[categoria["id"]].value = self._texto_categoria(
                categoria,
                activos,
            )

    def _refrescar_estado(self) -> None:
        """Sincroniza contador, ayuda y disponibilidad del botón."""
        total = sum(1 for peso in self.pesos.values() if peso > 0)
        listo = bool(self.destino and total)
        self.contador_parametros.value = (
            f"{total} de {self.total_parametros} activos"
        )
        self.ayuda_boton.value = self._texto_ayuda(listo)
        self.boton.disabled = not listo

    def _texto_ayuda(self, listo: bool) -> str:
        """Explica qué falta para habilitar la búsqueda."""
        activos = sum(1 for peso in self.pesos.values() if peso > 0)
        if not self.destino and not activos:
            return "Elegí un destino y al menos un parámetro para buscar."
        if not self.destino:
            return "Falta elegir un destino."
        if not activos:
            return "Falta activar al menos un parámetro."
        if listo:
            destino = "Luna" if self.destino == "luna" else "Marte"
            cantidad = (
                "1 parámetro"
                if activos == 1
                else f"{activos} parámetros"
            )
            return f"Listo para comparar {cantidad} con {destino}."
        return ""

    @staticmethod
    def _texto_categoria(categoria: dict, activos: int) -> str:
        """Resumen breve de una categoría."""
        total = len(categoria["parametros"])
        return f"{activos} de {total} activos"

    def _buscar(self, _: ft.Event[ft.FilledButton]) -> None:
        """Entrega la selección válida al llamador."""
        pesos_activos = {
            parametro: peso
            for parametro, peso in self.pesos.items()
            if peso > 0
        }
        if not self.destino or not pesos_activos:
            return
        if self.al_buscar is not None:
            self.al_buscar(self.destino, pesos_activos)
