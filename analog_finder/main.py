"""Punto de entrada de Analog Finder.

Hito 6: desde cada resultado se abre un mapamundi con todos los sitios del
ranking, sus marcadores clickeables y el sitio de origen resaltado. El
historial persistente del hito 5 se mantiene en la barra lateral.
"""

import asyncio
import traceback

import flet as ft

from core.logic import ResultadoAnalogo, rankear_sitios
from core.repository import (
    ErrorDatos,
    borrar_busqueda,
    cargar_categorias,
    cargar_destinos,
    cargar_historial,
    cargar_sitios,
    guardar_busqueda,
)
from ui.map_view import construir_vista_mapa
from ui.results_view import (
    construir_vista_cargando,
    construir_vista_error,
    construir_vista_resultados,
)
from ui.search_view import VistaBusqueda
from ui.sidebar import BarraLateral
from ui.theme import COLORES, RADIO, TEXTO, aplicar_tema


def _aviso(page: ft.Page, mensaje: str) -> None:
    """Muestra un aviso breve con el estilo de la app."""
    page.show_dialog(
        ft.SnackBar(
            content=ft.Text(
                mensaje,
                size=TEXTO["cuerpo"],
                color=COLORES["texto"],
            ),
            bgcolor=COLORES["superficie_alta"],
            shape=ft.RoundedRectangleBorder(radius=RADIO["md"]),
            show_close_icon=True,
        )
    )


def construir_pantalla(page: ft.Page) -> ft.Row:
    """Arma la app y conecta historial, búsqueda, ranking y resultados."""
    categorias = cargar_categorias()
    destinos = cargar_destinos()
    sitios = cargar_sitios()

    try:
        historial = cargar_historial()
    except ErrorDatos as error:
        historial = []
        error_historial: str | None = str(error)
    else:
        error_historial = None

    contenido = ft.Container(expand=True)
    resultados_actuales: list[ResultadoAnalogo] = []
    destino_actual: dict | None = None
    vista_resultados: ft.Container | None = None

    def mostrar_busqueda(reiniciar: bool = False) -> None:
        """Vuelve a la búsqueda, opcionalmente con la selección limpia."""
        if reiniciar:
            vista_busqueda.reiniciar()
        contenido.content = vista_busqueda.raiz
        contenido.update()

    def mostrar_resultados() -> None:
        """Restaura la pantalla de resultados que abrió el mapa."""
        if vista_resultados is None:
            mostrar_busqueda()
            return
        contenido.content = vista_resultados
        contenido.update()

    def al_ver_mapa(sitio: dict) -> None:
        """Abre el mapamundi con el sitio elegido como origen resaltado."""
        if not resultados_actuales or destino_actual is None:
            _aviso(page, "There are no results to show on the map.")
            return
        contenido.content = construir_vista_mapa(
            resultados_actuales,
            destino_actual,
            sitio["id"],
            al_volver=mostrar_resultados,
        )
        contenido.update()

    async def calcular(
        destino_id: str,
        pesos: dict,
        guardar: bool,
    ) -> None:
        """Muestra carga, calcula el ranking y presenta el resultado real."""
        nonlocal historial, error_historial
        nonlocal resultados_actuales, destino_actual, vista_resultados
        destino = next(
            (item for item in destinos if item["id"] == destino_id),
            None,
        )
        if destino is None:
            contenido.content = construir_vista_error(
                f"No se encontró el destino '{destino_id}'.",
                mostrar_busqueda,
            )
            contenido.update()
            return

        contenido.content = construir_vista_cargando(destino)
        contenido.update()
        # Cede un frame para que el estado de carga llegue a pintarse.
        await asyncio.sleep(0.05)

        try:
            resultados = rankear_sitios(sitios, destino, pesos)
        except Exception as error:
            traceback.print_exc()
            contenido.content = construir_vista_error(
                str(error),
                mostrar_busqueda,
            )
            contenido.update()
            return

        if guardar:
            try:
                entrada = guardar_busqueda(destino, pesos, categorias)
            except (ErrorDatos, ValueError) as error:
                _aviso(page, f"No se pudo guardar la búsqueda: {error}")
            else:
                historial.insert(0, entrada)
                error_historial = None
                barra.refrescar(historial)
                barra.raiz.update()

        resultados_actuales = resultados
        destino_actual = destino
        parametros = list(pesos)
        vista_resultados = construir_vista_resultados(
            resultados,
            categorias,
            destino,
            parametros,
            al_volver=mostrar_busqueda,
            al_ver_mapa=al_ver_mapa,
            pesos=pesos,
        )
        contenido.content = vista_resultados
        contenido.update()

    def al_buscar(destino_id: str, pesos: dict) -> None:
        """Lanza la búsqueda manual y guarda el resultado en el historial."""
        page.run_task(calcular, destino_id, pesos, True)

    def al_abrir_historial(entrada: dict) -> None:
        """Reabre una búsqueda guardada sin duplicarla."""
        pesos = entrada.get("pesos")
        if not isinstance(pesos, dict):
            pesos = {
                parametro: 5 for parametro in entrada.get("parametros", [])
            }
        page.run_task(
            calcular,
            entrada["destino_id"],
            pesos,
            False,
        )

    def al_borrar_historial(entrada_id: str) -> None:
        """Borra una entrada y repinta la barra lateral."""
        nonlocal historial, error_historial
        try:
            historial = borrar_busqueda(entrada_id)
        except (ErrorDatos, ValueError) as error:
            _aviso(page, f"No se pudo borrar la búsqueda: {error}")
            return
        error_historial = None
        barra.refrescar(historial)
        barra.raiz.update()

    def al_nueva_busqueda() -> None:
        """Limpia la selección y vuelve a la pantalla de búsqueda."""
        mostrar_busqueda(reiniciar=True)

    vista_busqueda = VistaBusqueda(categorias, al_buscar)
    barra = BarraLateral(
        historial,
        al_abrir=al_abrir_historial,
        al_borrar=al_borrar_historial,
        al_nueva=al_nueva_busqueda,
        error=error_historial,
    )
    contenido.content = vista_busqueda.raiz

    return ft.Row(
        controls=[
            barra.raiz,
            contenido,
        ],
        spacing=0,
        expand=True,
    )


def main(page: ft.Page):
    """Configura la página y monta la pantalla principal."""
    aplicar_tema(page)
    page.add(construir_pantalla(page))


if __name__ == "__main__":
    ft.run(main)
