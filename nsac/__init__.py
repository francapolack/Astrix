"""nsac — acceso a las fuentes de datos del reto Space Apps 2026.

Reto: "Identify Earth Locations that Analog the Permanent Moon Base
Locations and Mars".

Cada subpaquete de `nsac.sources` envuelve una API pública concreta:

    earthdata   NASA CMR + GIBS (Earthdata Search / Worldview)
    pds         PDS Search API, listados HTTP y ODE/GDS REST (PDS + LRO)
    usgs_stac   STAC de USGS Astrogeology (LOLA, Kaguya, HiRISE, CTX...)
    copernicus  Copernicus Data Space (STAC + OData)
    earthcode   ESA Open Science Data (STAC EarthCODE)
    csa         CSA Canadá: CKAN, datos abiertos RCM y EODMS
    asf         Alaska Satellite Facility (SAR de Earth)
    trek        NASA Solar System Treks (teselas WMTS de Luna y Marte)
    jaxa        JAXA G-Portal / AW3D30 (requiere cuenta)
"""

__version__ = "0.1.0"
