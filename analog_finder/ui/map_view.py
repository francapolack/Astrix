"""Pantalla de mapa: ubicación geográfica de los sitios del ranking.

La vista recibe ``ResultadoAnalogo`` ya calculados. No lee archivos ni
recalcula similitudes: dibuja un marcador por sitio y muestra el nombre y el
porcentaje que ya vienen del ranking.
"""

from collections.abc import Callable
from math import cos, hypot, radians

import flet as ft
import flet_map as fm

from core.logic import ResultadoAnalogo
from ui.theme import COLORES, ESPACIO, RADIO, TEXTO

URL_TILES = "https://tile.openstreetmap.org/{z}/{x}/{y}.png"
ATRIBUCION = "© OpenStreetMap contributors"
NOMBRE_PAQUETE = "AnalogFinder/1.0 (NASA Space Apps 2026)"
# Evita que el mundo se repita y duplique los marcadores en ventanas anchas.
ZOOM_MINIMO = 1.2
# Radio de toque alrededor de un marcador, en grados geográficos.
RADIO_TOQUE = 10.0


def _porcentaje(valor: float) -> int:
    """Convierte un puntaje normalizado en un porcentaje entero visible."""
    return round(valor * 100)


def _coordenadas(lat: float, lon: float) -> str:
    """Formatea una coordenada para leerla sin el mapa."""
    hemisferio_lat = "S" if lat < 0 else "N"
    hemisferio_lon = "O" if lon < 0 else "E"
    return (
        f"{abs(lat):.1f}° {hemisferio_lat} · "
        f"{abs(lon):.1f}° {hemisferio_lon}"
    )


def _encabezado(
    destino: dict,
    cantidad: int,
    al_volver: Callable[[], None],
) -> ft.Row:
    """Título, resumen y acción para volver a los resultados."""
    if cantidad == 1:
        detalle_sitios = "1 sitio comparado"
    else:
        detalle_sitios = f"{cantidad} sitios comparados"

    return ft.Row(
        controls=[
            ft.Column(
                controls=[
                    ft.Text(
                        "Mapa de análogos",
                        size=TEXTO["titulo"],
                        weight=ft.FontWeight.W_700,
                        color=COLORES["texto"],
                    ),
                    ft.Text(
                        f"{detalle_sitios} con {destino['nombre']}.",
                        size=TEXTO["cuerpo"],
                        color=COLORES["texto_tenue"],
                    ),
                ],
                spacing=0,
                expand=True,
            ),
            ft.OutlinedButton(
                content="Volver a resultados",
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
            ),
        ],
        spacing=ESPACIO["sm"],
        vertical_alignment=ft.CrossAxisAlignment.CENTER,
    )


def _leyenda() -> ft.Row:
    """Explica los marcadores y recuerda el carácter ilustrativo de los datos."""
    return ft.Row(
        controls=[
            ft.Row(
                controls=[
                    ft.Icon(
                        ft.Icons.STAR,
                        color=COLORES["aviso"],
                        size=16,
                    ),
                    ft.Text(
                        "Origen del mapa",
                        size=TEXTO["cuerpo"],
                        color=COLORES["texto_secundario"],
                    ),
                ],
                spacing=ESPACIO["xs"],
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            ft.Row(
                controls=[
                    ft.Icon(
                        ft.Icons.LOCATION_ON,
                        color=COLORES["acento"],
                        size=16,
                    ),
                    ft.Text(
                        "Sitios del ranking · tocá un marcador",
                        size=TEXTO["cuerpo"],
                        color=COLORES["texto_secundario"],
                    ),
                ],
                spacing=ESPACIO["xs"],
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            ft.Row(
                controls=[
                    ft.Icon(
                        ft.Icons.SCIENCE,
                        color=COLORES["aviso"],
                        size=16,
                    ),
                    ft.Text(
                        "Datos de ejemplo",
                        size=TEXTO["cuerpo"],
                        color=COLORES["aviso"],
                    ),
                ],
                spacing=ESPACIO["xs"],
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
        ],
        spacing=ESPACIO["sm"],
        run_spacing=ESPACIO["xs"],
        wrap=True,
        vertical_alignment=ft.CrossAxisAlignment.CENTER,
    )


def _aviso_tiles() -> ft.Container:
    """Plan B visible cuando el proveedor de tiles no responde."""
    return ft.Container(
        visible=False,
        left=ESPACIO["sm"],
        right=ESPACIO["sm"],
        top=ESPACIO["sm"],
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
                    ft.Icons.WIFI_OFF,
                    color=COLORES["aviso"],
                    size=20,
                ),
                ft.Text(
                    "No pudimos cargar las imágenes del mapa. Sin conexión o "
                    "con el proveedor de tiles fuera de servicio, los "
                    "marcadores siguen visibles sobre el fondo oscuro.",
                    size=TEXTO["cuerpo"],
                    color=COLORES["texto_secundario"],
                    expand=True,
                ),
            ],
            spacing=ESPACIO["xs"],
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        ),
    )


def _marcador(
    resultado: ResultadoAnalogo,
) -> tuple[fm.Marker, ft.Container, ft.Icon]:
    """Marcador con su contenedor e ícono para repintar."""
    sitio = resultado.sitio
    contenedor = ft.Container(
        width=40,
        height=40,
        border_radius=RADIO["xl"],
        alignment=ft.Alignment.CENTER,
        tooltip=f"{sitio['nombre']} · {_porcentaje(resultado.total)} %",
    )
    icono = ft.Icon(ft.Icons.LOCATION_ON, size=28)
    contenedor.content = icono
    marcador = fm.Marker(
        content=contenedor,
        coordinates=fm.MapLatitudeLongitude(
            latitude=sitio["lat"],
            longitude=sitio["lon"],
        ),
        width=40,
        height=40,
    )
    return marcador, contenedor, icono


def _sitio_mas_cercano(
    resultados: list[ResultadoAnalogo],
    latitud: float,
    longitud: float,
) -> ResultadoAnalogo | None:
    """Busca el sitio dentro del radio de toque de un clic en el mapa."""
    mejor: ResultadoAnalogo | None = None
    mejor_distancia = RADIO_TOQUE
    for resultado in resultados:
        sitio = resultado.sitio
        distancia_lat = sitio["lat"] - latitud
        distancia_lon = (sitio["lon"] - longitud) * cos(
            radians((sitio["lat"] + latitud) / 2)
        )
        distancia = hypot(distancia_lat, distancia_lon)
        if distancia <= mejor_distancia:
            mejor = resultado
            mejor_distancia = distancia
    return mejor


def _pintar_marcador(
    contenedor: ft.Container,
    icono: ft.Icon,
    es_origen: bool,
    es_seleccionado: bool,
) -> None:
    """Aplica el estado visual de origen y selección a un marcador."""
    if es_origen and es_seleccionado:
        contenedor.bgcolor = COLORES["aviso"]
        contenedor.border = ft.Border.all(2, COLORES["texto"])
        icono.icon = ft.Icons.STAR
        icono.color = COLORES["fondo"]
    elif es_origen:
        contenedor.bgcolor = COLORES["aviso_fondo"]
        contenedor.border = ft.Border.all(2, COLORES["aviso"])
        icono.icon = ft.Icons.STAR
        icono.color = COLORES["aviso"]
    elif es_seleccionado:
        contenedor.bgcolor = COLORES["acento"]
        contenedor.border = ft.Border.all(2, COLORES["acento_fuerte"])
        icono.icon = ft.Icons.LOCATION_ON
        icono.color = COLORES["fondo"]
    else:
        contenedor.bgcolor = COLORES["acento_suave"]
        contenedor.border = ft.Border.all(1, COLORES["borde"])
        icono.icon = ft.Icons.LOCATION_ON
        icono.color = COLORES["acento"]


def _tarjeta_detalle() -> tuple[ft.Container, dict[str, ft.Control]]:
    """Tarjeta que muestra el sitio elegido y su similitud."""
    icono = ft.Icon(ft.Icons.LOCATION_ON, color=COLORES["acento"], size=28)
    nombre = ft.Text(
        "",
        size=TEXTO["subtitulo"],
        weight=ft.FontWeight.W_700,
        color=COLORES["texto"],
        max_lines=1,
        overflow=ft.TextOverflow.ELLIPSIS,
    )
    origen = ft.Container(
        visible=False,
        padding=ft.Padding.symmetric(
            horizontal=ESPACIO["xs"],
            vertical=2,
        ),
        bgcolor=COLORES["aviso_fondo"],
        border=ft.Border.all(1, COLORES["aviso_borde"]),
        border_radius=RADIO["sm"],
        content=ft.Text(
            "Origen del mapa",
            size=TEXTO["cuerpo"],
            color=COLORES["aviso"],
        ),
    )
    detalle = ft.Text(
        "",
        size=TEXTO["cuerpo"],
        color=COLORES["texto_secundario"],
        max_lines=1,
        overflow=ft.TextOverflow.ELLIPSIS,
    )
    porcentaje = ft.Text(
        "",
        size=TEXTO["titulo"],
        weight=ft.FontWeight.W_700,
        color=COLORES["acento"],
    )
    etiqueta = ft.Text(
        "similitud",
        size=TEXTO["cuerpo"],
        color=COLORES["texto_tenue"],
    )

    tarjeta = ft.Container(
        padding=ft.Padding.all(ESPACIO["sm"]),
        bgcolor=COLORES["superficie_alterna"],
        border=ft.Border.all(1, COLORES["borde_suave"]),
        border_radius=RADIO["lg"],
        content=ft.Row(
            controls=[
                ft.Container(
                    width=48,
                    height=48,
                    bgcolor=COLORES["acento_suave"],
                    border_radius=RADIO["md"],
                    alignment=ft.Alignment.CENTER,
                    content=icono,
                ),
                ft.Column(
                    controls=[
                        ft.Row(
                            controls=[
                                ft.Container(
                                    content=nombre,
                                    expand=True,
                                ),
                                origen,
                            ],
                            spacing=ESPACIO["xs"],
                            vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        ),
                        detalle,
                    ],
                    spacing=ESPACIO["xs"],
                    expand=True,
                ),
                ft.Column(
                    controls=[porcentaje, etiqueta],
                    spacing=0,
                    horizontal_alignment=ft.CrossAxisAlignment.END,
                ),
            ],
            spacing=ESPACIO["sm"],
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        ),
    )
    controles = {
        "icono": icono,
        "nombre": nombre,
        "origen": origen,
        "detalle": detalle,
        "porcentaje": porcentaje,
    }
    return tarjeta, controles


def _estado_vacio(al_volver: Callable[[], None]) -> ft.Container:
    """Estado sin sitios para ubicar en el mapa."""
    return ft.Container(
        expand=True,
        bgcolor=COLORES["fondo"],
        alignment=ft.Alignment.CENTER,
        content=ft.Column(
            controls=[
                ft.Icon(
                    ft.Icons.MAP_OUTLINED,
                    color=COLORES["texto_tenue"],
                    size=48,
                ),
                ft.Text(
                    "No hay sitios para ubicar en el mapa",
                    size=TEXTO["subtitulo"],
                    weight=ft.FontWeight.W_600,
                    color=COLORES["texto"],
                    text_align=ft.TextAlign.CENTER,
                ),
                ft.Text(
                    "Volvé a los resultados y probá con otro destino u otros "
                    "parámetros.",
                    size=TEXTO["cuerpo"],
                    color=COLORES["texto_secundario"],
                    text_align=ft.TextAlign.CENTER,
                ),
                ft.OutlinedButton(
                    content="Volver a resultados",
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
                ),
            ],
            spacing=ESPACIO["xs"],
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
        ),
    )


def construir_vista_mapa(
    resultados: list[ResultadoAnalogo],
    destino: dict,
    sitio_origen_id: str,
    al_volver: Callable[[], None],
) -> ft.Container:
    """Devuelve el mapa con un marcador clickeable por sitio del ranking."""
    if not resultados:
        return _estado_vacio(al_volver)

    ids = {resultado.sitio["id"] for resultado in resultados}
    seleccionado = (
        sitio_origen_id if sitio_origen_id in ids else resultados[0].sitio["id"]
    )

    marcadores: dict[str, tuple[ft.Container, ft.Icon]] = {}
    tarjeta, textos = _tarjeta_detalle()
    aviso_tiles = _aviso_tiles()
    por_id = {resultado.sitio["id"]: resultado for resultado in resultados}

    def pintar_detalle(resultado: ResultadoAnalogo) -> None:
        """Actualiza la tarjeta con el sitio elegido."""
        sitio = resultado.sitio
        textos["icono"].icon = (
            ft.Icons.STAR if sitio["id"] == sitio_origen_id else ft.Icons.LOCATION_ON
        )
        textos["icono"].color = (
            COLORES["aviso"]
            if sitio["id"] == sitio_origen_id
            else COLORES["acento"]
        )
        textos["nombre"].value = sitio["nombre"]
        textos["origen"].visible = sitio["id"] == sitio_origen_id
        textos["detalle"].value = (
            f"{sitio['pais']} · {_coordenadas(sitio['lat'], sitio['lon'])}"
        )
        textos["porcentaje"].value = f"{_porcentaje(resultado.total)} %"

    def al_seleccionar(resultado: ResultadoAnalogo) -> None:
        """Repinta los marcadores y la tarjeta al tocar un sitio."""
        nonlocal seleccionado
        seleccionado = resultado.sitio["id"]
        for sitio_id, (contenedor, icono) in marcadores.items():
            _pintar_marcador(
                contenedor,
                icono,
                es_origen=sitio_id == sitio_origen_id,
                es_seleccionado=sitio_id == seleccionado,
            )
            contenedor.update()
        pintar_detalle(resultado)
        tarjeta.update()

    capa_marcadores = fm.MarkerLayer(markers=[])
    for resultado in resultados:
        marcador, contenedor, icono = _marcador(resultado)
        marcadores[resultado.sitio["id"]] = (contenedor, icono)
        capa_marcadores.markers.append(marcador)

    for sitio_id, (contenedor, icono) in marcadores.items():
        _pintar_marcador(
            contenedor,
            icono,
            es_origen=sitio_id == sitio_origen_id,
            es_seleccionado=sitio_id == seleccionado,
        )
    pintar_detalle(por_id[seleccionado])

    coordenadas = [
        fm.MapLatitudeLongitude(
            latitude=resultado.sitio["lat"],
            longitude=resultado.sitio["lon"],
        )
        for resultado in resultados
    ]
    if len(coordenadas) == 1:
        encuadre: dict = {
            "initial_center": coordenadas[0],
            "initial_zoom": 3,
        }
    else:
        encuadre = {
            "initial_camera_fit": fm.CameraFit(
                coordinates=coordenadas,
                padding=ft.Padding.all(ESPACIO["lg"]),
                min_zoom=ZOOM_MINIMO,
                max_zoom=4,
            ),
        }

    capa_tiles = fm.TileLayer(
        url_template=URL_TILES,
        user_agent_package_name=NOMBRE_PAQUETE,
    )

    def al_tocar_mapa(evento: fm.MapTapEvent) -> None:
        """Selecciona el marcador más cercano al punto tocado."""
        resultado = _sitio_mas_cercano(
            resultados,
            evento.coordinates.latitude,
            evento.coordinates.longitude,
        )
        if resultado is not None:
            al_seleccionar(resultado)

    mapa = fm.Map(
        expand=True,
        bgcolor=COLORES["fondo"],
        min_zoom=ZOOM_MINIMO,
        max_zoom=18,
        on_tap=al_tocar_mapa,
        layers=[
            capa_tiles,
            capa_marcadores,
            fm.SimpleAttribution(
                text=ATRIBUCION,
                text_style=ft.TextStyle(
                    size=TEXTO["cuerpo"],
                    color=COLORES["texto_secundario"],
                ),
                bgcolor=COLORES["superficie_alta"],
            ),
        ],
        **encuadre,
    )

    raiz = ft.Container(
        expand=True,
        bgcolor=COLORES["fondo"],
        padding=ft.Padding.all(ESPACIO["lg"]),
        content=ft.Column(
            controls=[
                _encabezado(destino, len(resultados), al_volver),
                _leyenda(),
                ft.Stack(
                    controls=[mapa, aviso_tiles],
                    expand=True,
                ),
                tarjeta,
            ],
            spacing=ESPACIO["xs"],
            expand=True,
        ),
    )

    def al_fallar_tile(_: ft.Event[fm.TileLayer] | None = None) -> None:
        """Muestra el plan B una sola vez, sin interrumpir los marcadores."""
        if aviso_tiles.visible:
            return
        aviso_tiles.visible = True
        raiz.update()

    capa_tiles.on_image_error = al_fallar_tile

    return raiz
