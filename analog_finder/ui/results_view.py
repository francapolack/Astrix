"""Pantalla de resultados: ranking de sitios análogos.

La vista recibe los resultados ya calculados: los del modo local
(`core/logic.py`, ejemplo) o los de la nube (`ResultadoNube`, con desglose
por categoría). No lee archivos ni recalcula similitudes: solo presenta
porcentajes, barras y textos que vienen de los datos.
"""

from collections.abc import Callable

import flet as ft

from core.logic import ResultadoAnalogo, ResultadoNube
from core.nube import CAMPOS_DATOS
from ui.theme import COLORES, ESPACIO, RADIO, TEXTO


def _porcentaje(valor: float) -> int:
    """Convierte un puntaje normalizado en un porcentaje entero visible."""
    return round(valor * 100)


def _formatear_valor(valor: float | None, unidad: str) -> str:
    """Texto del valor crudo con su unidad; None es honesto: sin dato."""
    if valor is None:
        return "sin dato en esta consulta"
    if unidad == "fracción":
        return f"{valor:.2f} frac."
    return f"{valor:g} {unidad}".strip()


def _subtitulo_sitio(sitio: dict) -> str:
    """Línea secundaria de la tarjeta: país (ejemplo) o tipo (nube)."""
    return sitio.get("pais") or sitio.get("tipo") or ""


def _aviso_datos(texto: str | None = None) -> ft.Container:
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
                    texto
                    or (
                        "Datos de ejemplo: los perfiles, las coordenadas y "
                        "los puntajes de esta versión son ilustrativos."
                    ),
                    size=TEXTO["cuerpo"],
                    color=COLORES["texto_secundario"],
                    expand=True,
                ),
            ],
            spacing=ESPACIO["xs"],
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        ),
    )


def _encabezado(
    destino: dict,
    parametros: list[str],
    cantidad: int,
    al_volver: Callable[[], None] | None,
) -> ft.Row:
    """Título, resumen y acción para volver a la búsqueda."""
    if len(parametros) == 1:
        detalle_parametros = "1 parámetro"
    else:
        detalle_parametros = f"{len(parametros)} parámetros"
    if cantidad == 1:
        detalle_sitios = "1 sitio comparado"
    else:
        detalle_sitios = f"{cantidad} sitios comparados"

    controles: list[ft.Control] = [
        ft.Column(
            controls=[
                ft.Text(
                    "Resultados",
                    size=TEXTO["titulo"],
                    weight=ft.FontWeight.W_700,
                    color=COLORES["texto"],
                ),
                ft.Text(
                    f"{detalle_sitios} con {destino['nombre']} · "
                    f"{detalle_parametros}.",
                    size=TEXTO["cuerpo"],
                    color=COLORES["texto_tenue"],
                ),
            ],
            spacing=0,
            expand=True,
        )
    ]
    if al_volver is not None:
        controles.append(
            ft.OutlinedButton(
                content="Volver a buscar",
                icon=ft.Icons.ARROW_BACK,
                on_click=lambda _: al_volver(),
                style=ft.ButtonStyle(
                    color=COLORES["texto"],
                    side=ft.BorderSide(1, COLORES["borde"]),
                    padding=ft.Padding.symmetric(
                        horizontal=ESPACIO["sm"],
                        vertical=ESPACIO["xs"],
                    ),
                    shape=ft.RoundedRectangleBorder(radius=RADIO["md"]),
                ),
            )
        )

    return ft.Row(
        controls=controles,
        spacing=ESPACIO["sm"],
        vertical_alignment=ft.CrossAxisAlignment.CENTER,
    )


def _texto_de_apoyo(
    titulo: str,
    icono: ft.IconData,
    color: str,
    texto: str,
) -> ft.Column:
    """Un bloque de texto de apoyo con su título e ícono."""
    return ft.Column(
        controls=[
            ft.Row(
                controls=[
                    ft.Icon(icono, color=color, size=20),
                    ft.Text(
                        titulo,
                        size=TEXTO["cuerpo_grande"],
                        weight=ft.FontWeight.W_600,
                        color=color,
                    ),
                ],
                spacing=ESPACIO["xs"],
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            ft.Text(
                texto,
                size=TEXTO["cuerpo"],
                color=COLORES["texto_secundario"],
            ),
        ],
        spacing=ESPACIO["xs"],
    )


def _barra_parametro(
    nombre: str,
    puntaje: float,
    detalle: str | None = None,
) -> ft.Column:
    """Etiqueta, detalle opcional, porcentaje y barra de un puntaje."""
    controles_derecha: list[ft.Control] = [
        ft.Text(
            f"{_porcentaje(puntaje)} %",
            size=TEXTO["cuerpo"],
            color=COLORES["texto_secundario"],
        ),
    ]
    if detalle:
        controles_derecha.insert(
            0,
            ft.Text(
                detalle,
                size=TEXTO["cuerpo"],
                color=COLORES["texto_tenue"],
            ),
        )
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
                    *controles_derecha,
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


def _grupos_de_categorias(
    resultado: ResultadoNube,
    categorias: list[dict],
) -> list[ft.Control]:
    """Una barra por cada categoría del desglose, en el orden del catálogo."""
    grupos: list[ft.Control] = []
    for categoria in categorias:
        puntaje = resultado.puntajes.get(categoria["id"])
        if puntaje is None:
            continue
        grupos.append(
            _barra_parametro(categoria["nombre"], puntaje, "categoría"),
        )
    return grupos


def _grupos_de_parametros(
    resultado: ResultadoAnalogo,
    categorias: list[dict],
    pesos: dict[str, int] | None = None,
) -> list[ft.Control]:
    """Agrupa los parámetros elegidos en el orden del catálogo."""
    pesos = pesos or {}
    seleccionados = set(resultado.puntajes)
    grupos: list[ft.Control] = []

    for categoria in categorias:
        parametros = [
            parametro
            for parametro in categoria["parametros"]
            if parametro["id"] in seleccionados
        ]
        if not parametros:
            continue
        grupos.append(
            ft.Column(
                controls=[
                    ft.Text(
                        categoria["nombre"],
                        size=TEXTO["cuerpo"],
                        weight=ft.FontWeight.W_600,
                        color=COLORES["texto_tenue"],
                    ),
                    *[
                        _barra_parametro(
                            parametro["nombre"],
                            resultado.puntajes[parametro["id"]],
                            f"peso {pesos.get(parametro['id'], 1)}",
                        )
                        for parametro in parametros
                    ],
                ],
                spacing=ESPACIO["xs"],
            )
        )
    return grupos


def _filas_campos_sitio(sitio: dict) -> list[ft.Control]:
    """Tabla con los 9 campos de datos del sitio (vacía si no hay).

    Los valores crudos viajan dentro del resultado (sitio["campos"]);
    la vista solo los presenta con su unidad.
    """
    campos = sitio.get("campos")
    if not isinstance(campos, dict) or not campos:
        return []
    filas: list[ft.Control] = []
    for clave_db, nombre, unidad in CAMPOS_DATOS:
        valor = campos.get(clave_db)
        tiene_dato = valor is not None
        filas.append(
            ft.Row(
                controls=[
                    ft.Text(
                        nombre,
                        size=TEXTO["cuerpo"],
                        color=COLORES["texto"],
                        width=180,
                    ),
                    ft.Text(
                        _formatear_valor(valor, unidad),
                        size=TEXTO["cuerpo"],
                        weight=ft.FontWeight.W_600,
                        color=(
                            COLORES["texto"]
                            if tiene_dato
                            else COLORES["aviso"]
                        ),
                        expand=True,
                    ),
                ],
                spacing=ESPACIO["xs"],
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            )
        )
    return filas


def _contenido_desplegable(
    resultado: ResultadoAnalogo | ResultadoNube,
    categorias: list[dict],
    al_ver_mapa: Callable[[dict], None] | None,
    pesos: dict[str, int] | None = None,
) -> ft.Container:
    """Detalle con textos, barras y acción de mapa."""
    textos = resultado.sitio["textos"]
    if isinstance(resultado, ResultadoNube):
        titulo_barras = "Similitud por categoría"
        grupos = _grupos_de_categorias(resultado, categorias)
    else:
        titulo_barras = "Similitud por parámetro"
        grupos = _grupos_de_parametros(resultado, categorias, pesos)

    controles: list[ft.Control] = [
        ft.Divider(height=1, thickness=1, color=COLORES["borde_suave"]),
        _texto_de_apoyo(
            "Qué es similar",
            ft.Icons.LIGHTBULB_OUTLINE,
            COLORES["exito"],
            textos["similar"],
        ),
        _texto_de_apoyo(
            "Dónde falla la analogía",
            ft.Icons.WARNING_AMBER_ROUNDED,
            COLORES["aviso"],
            textos["falla"],
        ),
        _texto_de_apoyo(
            "Para qué sirve en una misión",
            ft.Icons.ROCKET_LAUNCH_OUTLINED,
            COLORES["acento"],
            textos["mision"],
        ),
        ft.Divider(height=1, thickness=1, color=COLORES["borde_suave"]),
        ft.Text(
            titulo_barras,
            size=TEXTO["cuerpo_grande"],
            weight=ft.FontWeight.W_600,
            color=COLORES["texto"],
        ),
        *grupos,
    ]
    filas_campos = _filas_campos_sitio(resultado.sitio)
    if filas_campos:
        controles.extend(
            [
                ft.Divider(height=1, thickness=1, color=COLORES["borde_suave"]),
                ft.Text(
                    "Datos del sitio (los 9 campos del catálogo)",
                    size=TEXTO["cuerpo_grande"],
                    weight=ft.FontWeight.W_600,
                    color=COLORES["texto"],
                ),
                *filas_campos,
            ]
        )
    if al_ver_mapa is not None:
        controles.append(
            ft.OutlinedButton(
                content="Ver mapa",
                icon=ft.Icons.MAP_OUTLINED,
                on_click=lambda _: al_ver_mapa(resultado.sitio),
                style=ft.ButtonStyle(
                    color=COLORES["texto"],
                    side=ft.BorderSide(1, COLORES["borde"]),
                    padding=ft.Padding.symmetric(
                        horizontal=ESPACIO["sm"],
                        vertical=ESPACIO["xs"],
                    ),
                    shape=ft.RoundedRectangleBorder(radius=RADIO["md"]),
                ),
            )
        )

    return ft.Container(
        visible=False,
        padding=ft.Padding.only(
            left=ESPACIO["sm"],
            right=ESPACIO["sm"],
            bottom=ESPACIO["sm"],
        ),
        content=ft.Column(controls=controles, spacing=ESPACIO["sm"]),
    )


def _crear_tarjeta(
    posicion: int,
    resultado: ResultadoAnalogo,
    categorias: list[dict],
    al_ver_mapa: Callable[[dict], None] | None,
    pesos: dict[str, int] | None = None,
) -> ft.Container:
    """Tarjeta desplegable de un sitio del ranking."""
    sitio = resultado.sitio
    flecha = ft.Icon(
        ft.Icons.EXPAND_MORE,
        color=COLORES["texto_secundario"],
        size=24,
    )
    detalle = _contenido_desplegable(resultado, categorias, al_ver_mapa, pesos)

    def alternar(_: ft.Event[ft.Container]) -> None:
        """Muestra u oculta el detalle de este resultado."""
        detalle.visible = not detalle.visible
        flecha.icon = (
            ft.Icons.EXPAND_LESS if detalle.visible else ft.Icons.EXPAND_MORE
        )
        raiz.update()

    encabezado = ft.Container(
        padding=ft.Padding.all(ESPACIO["sm"]),
        ink=True,
        on_click=alternar,
        content=ft.Column(
            controls=[
                ft.Row(
                    controls=[
                        ft.Container(
                            width=40,
                            height=40,
                            border_radius=RADIO["md"],
                            bgcolor=COLORES["acento_suave"],
                            alignment=ft.Alignment.CENTER,
                            content=ft.Text(
                                str(posicion),
                                size=TEXTO["cuerpo_grande"],
                                weight=ft.FontWeight.W_700,
                                color=COLORES["acento"],
                            ),
                        ),
                        ft.Column(
                            controls=[
                                ft.Text(
                                    sitio["nombre"],
                                    size=TEXTO["subtitulo"],
                                    weight=ft.FontWeight.W_700,
                                    color=COLORES["texto"],
                                ),
                                ft.Text(
                                    _subtitulo_sitio(sitio),
                                    size=TEXTO["cuerpo"],
                                    color=COLORES["texto_secundario"],
                                ),
                            ],
                            spacing=0,
                            expand=True,
                        ),
                        ft.Column(
                            controls=[
                                ft.Text(
                                    f"{_porcentaje(resultado.total)} %",
                                    size=TEXTO["titulo"],
                                    weight=ft.FontWeight.W_700,
                                    color=COLORES["acento"],
                                ),
                                ft.Text(
                                    "similitud",
                                    size=TEXTO["cuerpo"],
                                    color=COLORES["texto_tenue"],
                                ),
                            ],
                            spacing=0,
                            horizontal_alignment=ft.CrossAxisAlignment.END,
                        ),
                        flecha,
                    ],
                    spacing=ESPACIO["sm"],
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                ft.ProgressBar(
                    value=resultado.total,
                    bar_height=8,
                    color=COLORES["acento"],
                    bgcolor=COLORES["superficie_alta"],
                    border_radius=RADIO["sm"],
                ),
            ],
            spacing=ESPACIO["xs"],
        ),
    )

    raiz = ft.Container(
        bgcolor=COLORES["superficie_alterna"],
        border=ft.Border.all(1, COLORES["borde_suave"]),
        border_radius=RADIO["lg"],
        clip_behavior=ft.ClipBehavior.ANTI_ALIAS,
        content=ft.Column(
            controls=[encabezado, detalle],
            spacing=0,
        ),
    )
    return raiz


def _marco(
    encabezado: ft.Control,
    contenido: ft.Control,
    aviso_texto: str | None = None,
) -> ft.Container:
    """Marco común de la pantalla de resultados."""
    return ft.Container(
        expand=True,
        bgcolor=COLORES["fondo"],
        padding=ft.Padding.all(ESPACIO["lg"]),
        content=ft.Column(
            controls=[
                encabezado,
                _aviso_datos(aviso_texto),
                contenido,
            ],
            spacing=ESPACIO["xs"],
            expand=True,
        ),
    )


def construir_vista_resultados(
    resultados: list[ResultadoAnalogo] | list[ResultadoNube],
    categorias: list[dict],
    destino: dict,
    parametros: list[str],
    al_volver: Callable[[], None] | None = None,
    al_ver_mapa: Callable[[dict], None] | None = None,
    pesos: dict[str, int] | None = None,
    aviso_texto: str | None = None,
) -> ft.Container:
    """Devuelve la lista ordenada de resultados lista para montar."""
    encabezado = _encabezado(
        destino,
        parametros,
        len(resultados),
        al_volver,
    )

    if not resultados:
        contenido = ft.Container(
            expand=True,
            alignment=ft.Alignment.CENTER,
            content=ft.Column(
                controls=[
                    ft.Icon(
                        ft.Icons.SEARCH_OFF,
                        color=COLORES["texto_tenue"],
                        size=48,
                    ),
                    ft.Text(
                        "No hay sitios para comparar",
                        size=TEXTO["subtitulo"],
                        weight=ft.FontWeight.W_600,
                        color=COLORES["texto"],
                        text_align=ft.TextAlign.CENTER,
                    ),
                    ft.Text(
                        "Probá con otro destino u otros parámetros.",
                        size=TEXTO["cuerpo"],
                        color=COLORES["texto_secundario"],
                        text_align=ft.TextAlign.CENTER,
                    ),
                ],
                spacing=ESPACIO["xs"],
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            ),
        )
        return _marco(encabezado, contenido, aviso_texto)

    lista = ft.Column(
        controls=[
            _crear_tarjeta(
                posicion,
                resultado,
                categorias,
                al_ver_mapa,
                pesos,
            )
            for posicion, resultado in enumerate(resultados, start=1)
        ],
        spacing=ESPACIO["sm"],
        scroll=ft.ScrollMode.AUTO,
        expand=True,
    )
    return _marco(encabezado, lista, aviso_texto)


def construir_vista_cargando(destino: dict) -> ft.Container:
    """Estado breve mientras se calcula el ranking."""
    return ft.Container(
        expand=True,
        bgcolor=COLORES["fondo"],
        alignment=ft.Alignment.CENTER,
        content=ft.Column(
            controls=[
                ft.ProgressRing(
                    width=48,
                    height=48,
                    stroke_width=4,
                    color=COLORES["acento"],
                    bgcolor=COLORES["superficie_alta"],
                ),
                ft.Text(
                    "Calculando análogos",
                    size=TEXTO["subtitulo"],
                    weight=ft.FontWeight.W_600,
                    color=COLORES["texto"],
                    text_align=ft.TextAlign.CENTER,
                ),
                ft.Text(
                    f"Comparando los sitios con {destino['nombre']}.",
                    size=TEXTO["cuerpo"],
                    color=COLORES["texto_secundario"],
                    text_align=ft.TextAlign.CENTER,
                ),
            ],
            spacing=ESPACIO["xs"],
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
        ),
    )


def construir_vista_error(
    mensaje: str,
    al_volver: Callable[[], None] | None = None,
) -> ft.Container:
    """Estado de error con el mensaje real y una salida clara."""
    controles: list[ft.Control] = [
        ft.Icon(
            ft.Icons.ERROR_OUTLINE,
            color=COLORES["error"],
            size=48,
        ),
        ft.Text(
            "No pudimos calcular el ranking",
            size=TEXTO["subtitulo"],
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
    ]
    if al_volver is not None:
        controles.append(
            ft.OutlinedButton(
                content="Volver a buscar",
                icon=ft.Icons.ARROW_BACK,
                on_click=lambda _: al_volver(),
                style=ft.ButtonStyle(
                    color=COLORES["texto"],
                    side=ft.BorderSide(1, COLORES["borde"]),
                    padding=ft.Padding.symmetric(
                        horizontal=ESPACIO["sm"],
                        vertical=ESPACIO["xs"],
                    ),
                    shape=ft.RoundedRectangleBorder(radius=RADIO["md"]),
                ),
            )
        )

    return ft.Container(
        expand=True,
        bgcolor=COLORES["fondo"],
        alignment=ft.Alignment.CENTER,
        content=ft.Container(
            padding=ft.Padding.all(ESPACIO["lg"]),
            bgcolor=COLORES["superficie_alterna"],
            border=ft.Border.all(1, COLORES["error"]),
            border_radius=RADIO["lg"],
            content=ft.Column(
                controls=controles,
                spacing=ESPACIO["xs"],
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            ),
        ),
    )
