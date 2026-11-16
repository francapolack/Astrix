"""Punto de entrada de Analog Finder.

El flujo va contra la nube (Supabase RPC v2, ver supabase/rpc_v2.sql):
1) el usuario elige destino y valores reales por parámetro,
2) el RPC devuelve el sitio de Luna/Marte que cumple esa preferencia,
3) una pantalla previa muestra ESE sitio (lugar de referencia),
4) con el mismo perfil se muestran los análogos terrestres y el mapa.
El historial persistente se mantiene en la barra lateral.
"""

import asyncio
import traceback

import flet as ft

from core.logic import ResultadoNube
from core.nube import (
    adaptar_sitio_nube,
    buscar_analogos,
    buscar_analogos_cuerpo,
    campos_de_datos,
    cargar_credenciales,
    construir_perfil,
    datos_sitio,
    extraer_sitio_objetivo,
    perfil_desde_datos,
)
from core.repository import (
    ErrorDatos,
    borrar_busqueda,
    cargar_categorias,
    cargar_historial,
    guardar_busqueda,
)
from ui.map_view import construir_vista_mapa
from ui.objetivo_view import construir_vista_objetivo
from ui.results_view import (
    construir_vista_cargando,
    construir_vista_error,
    construir_vista_resultados,
)
from ui.search_view import DESTINOS, VistaBusqueda
from ui.sidebar import BarraLateral
from ui.theme import COLORES, RADIO, TEXTO, aplicar_tema

AVISO_DATOS_REALES = (
    "Datos reales: los resultados provienen de la base de datos del "
    "proyecto (Supabase)."
)


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
    """Arma la app y conecta búsqueda, sitio objetivo, resultados y mapa."""
    categorias = cargar_categorias()

    try:
        historial = cargar_historial()
    except ErrorDatos as error:
        historial = []
        error_historial: str | None = str(error)
    else:
        error_historial = None

    contenido = ft.Container(expand=True)
    resultados_actuales: list[ResultadoNube] = []
    destino_actual: dict | None = None
    vista_resultados: ft.Container | None = None
    # Filas de Tierra (buscadas con el perfil COMPLETO del sitio objetivo)
    # y la selección del usuario, pendientes de pasar a resultados.
    filas_tierra_pendiente: list[dict] | None = None
    seleccion_pendiente: dict[str, float] = {}
    guardar_pendiente = False

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
            _aviso(page, "No hay resultados para mostrar en el mapa.")
            return
        contenido.content = construir_vista_mapa(
            resultados_actuales,
            destino_actual,
            sitio["id"],
            al_volver=mostrar_resultados,
        )
        contenido.update()

    def mostrar_error(mensaje: str) -> None:
        """Muestra el error real y da salida a la búsqueda."""
        traceback.print_exc()
        contenido.content = construir_vista_error(mensaje, mostrar_busqueda)
        contenido.update()

    async def calcular(destino_id: str, seleccion: dict[str, float]) -> None:
        """Consulta la nube: perfil del usuario → sitio objetivo → datos."""
        nonlocal historial, error_historial
        nonlocal filas_tierra_pendiente, seleccion_pendiente
        destino = next(
            (item for item in DESTINOS if item["id"] == destino_id),
            None,
        )
        if destino is None:
            mostrar_error(f"No se encontró el destino '{destino_id}'.")
            return

        contenido.content = construir_vista_cargando(destino)
        contenido.update()
        # Cede un frame para que el estado de carga llegue a pintarse.
        await asyncio.sleep(0.05)

        try:
            perfil = construir_perfil(categorias, seleccion)
            url, clave = cargar_credenciales()
            # HTTP en un hilo aparte: la UI no se congela mientras llega
            # la respuesta (la función es bloqueante por naturaleza).
            respuesta = await asyncio.to_thread(
                buscar_analogos, url, clave, perfil
            )
            objetivo = extraer_sitio_objetivo(respuesta, destino_id)
            datos = await asyncio.to_thread(
                datos_sitio, url, clave, objetivo["sitio_id"]
            )
            # El sitio completo manda: los análogos terrestres se buscan
            # con TODOS sus campos con valor (más precisión que el
            # perfil inicial del usuario).
            perfil_completo = perfil_desde_datos(datos)
            filas_tierra = await asyncio.to_thread(
                buscar_analogos_cuerpo,
                url,
                clave,
                perfil_completo,
                "tierra",
                5,
            )
        except Exception as error:
            # Se muestra el error real y el traceback queda en consola;
            # nunca se queda la pantalla de carga colgada.
            mostrar_error(str(error))
            return

        filas_tierra_pendiente = filas_tierra
        seleccion_pendiente = dict(seleccion)

        contenido.content = construir_vista_objetivo(
            objetivo,
            datos,
            destino,
            categorias,
            seleccion,
            AVISO_DATOS_REALES,
            al_volver=mostrar_busqueda,
            al_continuar=lambda: page.run_task(ir_a_resultados),
        )
        contenido.update()

    async def ir_a_resultados() -> None:
        """Pasa de la pantalla del sitio objetivo a los análogos terrestres."""
        nonlocal historial, error_historial
        nonlocal resultados_actuales, vista_resultados
        nonlocal guardar_pendiente
        if filas_tierra_pendiente is None:
            mostrar_busqueda()
            return
        destino = destino_actual or DESTINOS[0]

        try:
            url, clave = cargar_credenciales()
            # Por cada análogo se traen sus 9 campos con valor para
            # mostrarlos en la tarjeta desplegable.
            datos_por_sitio = await asyncio.gather(
                *[
                    asyncio.to_thread(
                        datos_sitio,
                        url,
                        clave,
                        fila.get("sitio_id"),
                    )
                    for fila in filas_tierra_pendiente
                ]
            )
            resultados = [
                adaptar_sitio_nube(
                    fila,
                    categorias,
                    campos=campos_de_datos(datos),
                )
                for fila, datos in zip(
                    filas_tierra_pendiente, datos_por_sitio
                )
            ]
        except Exception as error:
            mostrar_error(str(error))
            return

        if guardar_pendiente:
            guardar_pendiente = False
            try:
                entrada = guardar_busqueda(
                    destino,
                    {p: 1 for p in seleccion_pendiente},
                    categorias,
                    valores=dict(seleccion_pendiente),
                )
            except (ErrorDatos, ValueError) as error:
                _aviso(page, f"No se pudo guardar la búsqueda: {error}")
            else:
                historial.insert(0, entrada)
                error_historial = None
                barra.refrescar(historial)
                barra.raiz.update()

        resultados_actuales = resultados
        vista_resultados = construir_vista_resultados(
            resultados,
            categorias,
            destino,
            list(seleccion_pendiente),
            al_volver=mostrar_busqueda,
            al_ver_mapa=al_ver_mapa,
            aviso_texto=AVISO_DATOS_REALES,
        )
        contenido.content = vista_resultados
        contenido.update()

    def al_buscar(destino_id: str, seleccion: dict[str, float]) -> None:
        """Lanza la búsqueda manual y guarda el resultado en el historial."""
        nonlocal destino_actual, guardar_pendiente
        destino_actual = next(
            (item for item in DESTINOS if item["id"] == destino_id),
            None,
        )
        guardar_pendiente = True
        page.run_task(calcular, destino_id, seleccion)

    def al_abrir_historial(entrada: dict) -> None:
        """Reabre una búsqueda guardada sin duplicarla."""
        nonlocal destino_actual, guardar_pendiente
        destino_actual = next(
            (
                item
                for item in DESTINOS
                if item["id"] == entrada["destino_id"]
            ),
            None,
        )
        guardar_pendiente = False
        valores = entrada.get("valores")
        seleccion: dict[str, float] = {}
        if isinstance(valores, dict):
            seleccion = {
                parametro: float(valor)
                for parametro, valor in valores.items()
            }
        if not seleccion:
            _aviso(
                page,
                "Esta entrada no guardó los valores elegidos; "
                "repetí la búsqueda para verla con valores reales.",
            )
            return
        page.run_task(calcular, entrada["destino_id"], seleccion)

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
