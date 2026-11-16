"""Pantalla de búsqueda: destino, parámetros y acción principal.

La vista maneja la selección visual, pero no calcula similitudes. Cuando la
selección es válida entrega el destino y los ids de los parámetros al llamador.
"""

from collections.abc import Callable

import flet as ft

from ui.theme import COLORES, ESPACIO, RADIO, TEXTO

# Los iconos son decisión visual de la interfaz, no un dato del catálogo.
# Los ids coinciden con las categorías del desglose de la nube.
ICONOS_CATEGORIA = {
    "topografia": ft.Icons.TERRAIN,
    "termico": ft.Icons.THERMOSTAT,
    "superficie": ft.Icons.GRAIN,
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
                                "Datos reales",
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
                    "Datos reales: los resultados provienen de la base de "
                    "datos del proyecto (Supabase). Los valores objetivo "
                    "los fija el usuario.",
                    size=TEXTO["cuerpo"],
                    color=COLORES["texto_secundario"],
                    expand=True,
                ),
            ],
            spacing=ESPACIO["xs"],
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        ),
    )


def _texto_valor(parametro: dict, valor: float) -> str:
    """Formatea un valor real con su unidad para la etiqueta del slider."""
    if parametro.get("unidad") == "fracción":
        return f"{valor:.2f} frac."
    return f"{valor:g} {parametro.get('unidad', '')}".strip()


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
    """Estado y controles de la pantalla de búsqueda.

    Cada parámetro tiene un interruptor y un slider con el VALOR REAL que
    el usuario quiere pedir (metros, grados, kelvin, fracción). Cuando la
    selección es válida entrega el destino y {id_parametro: valor} al
    llamador; el perfil para la nube lo arma core/nube.py.
    """

    def __init__(
        self,
        categorias: list[dict],
        al_buscar: Callable[[str, dict[str, float]], None] | None = None,
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
        # Valor del slider (real) y parámetros activados por interruptor.
        self.valores: dict[str, float] = {
            parametro["id"]: self._valor_inicial(parametro)
            for categoria in categorias
            for parametro in categoria["parametros"]
        }
        self.usados: set[str] = set()
        self.tarjetas: dict[str, ft.Container] = {}
        self.marcas: dict[str, ft.Icon] = {}
        self.deslizadores: dict[str, ft.Slider] = {}
        self.etiquetas_valor: dict[str, ft.Text] = {}
        self.interruptores: dict[str, ft.Switch] = {}
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

    @staticmethod
    def _valor_inicial(parametro: dict) -> float:
        """Valor por defecto del slider: el punto medio del rango real."""
        minimo = float(parametro.get("min", 0.0))
        maximo = float(parametro.get("max", 1.0))
        return round((minimo + maximo) / 2, 2)

    def _crear_slider(self, parametro: dict) -> ft.Row:
        """Interruptor + slider del VALOR REAL de un parámetro."""
        parametro_id = parametro["id"]
        minimo = float(parametro.get("min", 0.0))
        maximo = float(parametro.get("max", 1.0))
        etiqueta = ft.Text(
            "—",
            size=TEXTO["cuerpo"],
            color=COLORES["texto_tenue"],
            width=120,
            text_align=ft.TextAlign.RIGHT,
        )
        self.etiquetas_valor[parametro_id] = etiqueta

        interruptor = ft.Switch(
            value=False,
            data=parametro_id,
            active_color=COLORES["acento"],
            scale=0.8,
            on_change=self._alternar_parametro,
        )
        self.interruptores[parametro_id] = interruptor

        deslizador = ft.Slider(
            min=minimo,
            max=maximo,
            divisions=40,
            value=self.valores[parametro_id],
            data=parametro_id,
            active_color=COLORES["acento"],
            inactive_color=COLORES["superficie_alta"],
            thumb_color=COLORES["acento_fuerte"],
            label=parametro["nombre"],
            on_change=self._cambiar_valor,
            on_change_end=self._refrescar_y_repintar,
            width=240,
        )
        self.deslizadores[parametro_id] = deslizador

        return ft.Row(
            controls=[
                interruptor,
                ft.Text(
                    parametro["nombre"],
                    size=TEXTO["cuerpo"],
                    color=COLORES["texto"],
                    width=140,
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

    def _alternar_parametro(self, evento: ft.Event[ft.Switch]) -> None:
        """Activa o desactiva un parámetro para la búsqueda."""
        parametro_id = evento.control.data
        if evento.control.value:
            self.usados.add(parametro_id)
            self.etiquetas_valor[parametro_id].value = _texto_valor(
                self._parametro(parametro_id),
                self.valores[parametro_id],
            )
            self.etiquetas_valor[parametro_id].color = COLORES["acento"]
        else:
            self.usados.discard(parametro_id)
            self.etiquetas_valor[parametro_id].value = "—"
            self.etiquetas_valor[parametro_id].color = COLORES["texto_tenue"]

        self._actualizar_subtitulos()
        self._refrescar_estado()
        self.raiz.update()

    def _cambiar_valor(self, evento: ft.Event[ft.Slider]) -> None:
        """Actualiza el valor real elegido para un parámetro."""
        parametro_id = evento.control.data
        self.valores[parametro_id] = float(evento.control.value or 0)
        self._refrescar_y_repintar()

    def _refrescar_y_repintar(self, *_: object) -> None:
        """Repinta etiquetas, contador y botón tras mover un slider."""
        for parametro_id in self.usados:
            self.etiquetas_valor[parametro_id].value = _texto_valor(
                self._parametro(parametro_id),
                self.valores[parametro_id],
            )
        self._actualizar_subtitulos()
        self._refrescar_estado()
        self.raiz.update()

    def _parametro(self, parametro_id: str) -> dict:
        """Devuelve la definición del parámetro del catálogo."""
        for categoria in self.categorias:
            for parametro in categoria["parametros"]:
                if parametro["id"] == parametro_id:
                    return parametro
        raise ValueError(
            f"El catálogo no tiene el parámetro '{parametro_id}'."
        )

    def reiniciar(self) -> None:
        """Limpia la selección y deja la pantalla como al inicio."""
        self.destino = None
        self.usados.clear()
        for categoria in self.categorias:
            for parametro in categoria["parametros"]:
                parametro_id = parametro["id"]
                self.valores[parametro_id] = self._valor_inicial(parametro)
                self.deslizadores[parametro_id].value = self.valores[
                    parametro_id
                ]
                self.interruptores[parametro_id].value = False
                self.etiquetas_valor[parametro_id].value = "—"
                self.etiquetas_valor[parametro_id].color = (
                    COLORES["texto_tenue"]
                )
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
                if parametro["id"] in self.usados
            )
            self.subtitulos[categoria["id"]].value = self._texto_categoria(
                categoria,
                activos,
            )

    def _refrescar_estado(self) -> None:
        """Sincroniza contador, ayuda y disponibilidad del botón."""
        total = len(self.usados)
        listo = bool(self.destino and total)
        self.contador_parametros.value = (
            f"{total} de {self.total_parametros} activos"
        )
        self.ayuda_boton.value = self._texto_ayuda(listo)
        self.boton.disabled = not listo

    def _texto_ayuda(self, listo: bool) -> str:
        """Explica qué falta para habilitar la búsqueda."""
        activos = len(self.usados)
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
        """Entrega la selección válida (valores reales) al llamador."""
        seleccion = {
            parametro_id: self.valores[parametro_id]
            for parametro_id in self.usados
        }
        if not self.destino or not seleccion:
            return
        if self.al_buscar is not None:
            self.al_buscar(self.destino, seleccion)
