"""Tema visual de Analog Finder: colores, tipografías y espaciados."""

import flet as ft

# Paleta espacial sobria. El cian identifica acciones y el ámbar a Marte.
COLORES = {
    "fondo": "#070B14",
    "superficie": "#0D1422",
    "superficie_alterna": "#111A2B",
    "superficie_alta": "#18243A",
    "borde": "#24324A",
    "borde_suave": "#1A263A",
    "texto": "#E8EEF9",
    "texto_secundario": "#A6B4C9",
    "texto_tenue": "#74849E",
    "acento": "#7DD3FC",
    "acento_fuerte": "#38BDF8",
    "acento_suave": "#123047",
    "luna": "#A5B4FC",
    "luna_suave": "#1C2442",
    "marte": "#FB923C",
    "marte_suave": "#3A2114",
    "exito": "#4ADE80",
    "aviso": "#FBBF24",
    "aviso_fondo": "#2A2211",
    "aviso_borde": "#5A4718",
    "error": "#F87171",
    "error_fondo": "#2A1518",
    "sombra": "#02040A",
}

# Escala de 8 px. Toda separación de layout debe salir de acá.
ESPACIO = {
    "xs": 8,
    "sm": 16,
    "md": 24,
    "lg": 32,
    "xl": 40,
    "xxl": 48,
    "xxxl": 64,
}

# Radios y tamaños de texto.
RADIO = {"sm": 8, "md": 12, "lg": 16, "xl": 20}
TEXTO = {
    "cuerpo": 14,
    "cuerpo_grande": 16,
    "subtitulo": 18,
    "titulo": 24,
    "encabezado": 32,
    "display": 40,
}

ANCHO_BARRA_LATERAL = 288
ANCHO_MINIMO = 1000
ALTO_MINIMO = 700


def _esquema_de_colores() -> ft.ColorScheme:
    """Devuelve el esquema Material 3 alineado con la paleta."""
    return ft.ColorScheme(
        primary=COLORES["acento"],
        on_primary=COLORES["fondo"],
        primary_container=COLORES["acento_suave"],
        on_primary_container=COLORES["texto"],
        secondary=COLORES["luna"],
        on_secondary=COLORES["fondo"],
        secondary_container=COLORES["luna_suave"],
        on_secondary_container=COLORES["texto"],
        tertiary=COLORES["marte"],
        on_tertiary=COLORES["fondo"],
        tertiary_container=COLORES["marte_suave"],
        on_tertiary_container=COLORES["texto"],
        surface=COLORES["superficie"],
        on_surface=COLORES["texto"],
        on_surface_variant=COLORES["texto_secundario"],
        outline=COLORES["borde"],
        outline_variant=COLORES["borde_suave"],
        error=COLORES["error"],
        on_error=COLORES["fondo"],
        error_container=COLORES["error_fondo"],
        on_error_container=COLORES["texto"],
        surface_container_lowest=COLORES["fondo"],
        surface_container_low=COLORES["superficie"],
        surface_container=COLORES["superficie_alterna"],
        surface_container_high=COLORES["superficie_alta"],
        surface_bright=COLORES["superficie_alta"],
    )


def aplicar_tema(page: ft.Page) -> None:
    """Configura ventana, modo oscuro y tema Material 3 de la app."""
    page.title = "Analog Finder — Análogos terrestres de Luna y Marte"
    page.theme_mode = ft.ThemeMode.DARK
    page.bgcolor = COLORES["fondo"]
    page.padding = 0

    tema = ft.Theme(
        use_material3=True,
        color_scheme=_esquema_de_colores(),
        font_family="Segoe UI",
        scaffold_bgcolor=COLORES["fondo"],
        card_bgcolor=COLORES["superficie"],
        divider_color=COLORES["borde"],
    )
    page.theme = tema
    page.dark_theme = tema

    page.window.width = 1280
    page.window.height = 720
    page.window.min_width = ANCHO_MINIMO
    page.window.min_height = ALTO_MINIMO
    page.window.bgcolor = COLORES["fondo"]
    page.window.resizable = True
