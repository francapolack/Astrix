from colector_datos import obtener_datos_sitio

datos = obtener_datos_sitio(cuerpo="luna", lat=-89.9, lon=0.05, radio=0.05, incluir_tierra=True)
# claves: metadatos / topografia / termico / superficie / iluminacion
# opcionales: con_teselas=True (URLs WMTS para Leaflet) · incluir_tierra=True
print(datos)