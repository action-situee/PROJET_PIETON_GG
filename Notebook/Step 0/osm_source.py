# osm_source.py
import geopandas as gpd
import osmnx as ox

OSM_SOURCE = "local"   # "local" | "overpass"
OSM_LOCAL_FILES = {
    "GG": {
        "full":    "../../Data/input/osm_raw/GG_clean.osm",
        "network": "../../Data/input/osm_raw/GG_network.osm",
    },
    "GE": {
        "full":    "../../Data/input/osm_raw/GE.osm",
        "network": "../../Data/input/osm_raw/GE_network.osm",
    },
}

def load_osm_features(polygon, tags, territory, geometry_types=None, variant="full"):
    path = OSM_LOCAL_FILES[territory][variant]
    gdf = ox.features_from_xml(path, polygon=polygon, tags=tags).reset_index()
    gdf = gpd.GeoDataFrame(gdf, geometry="geometry", crs="EPSG:4326")
    if geometry_types:
        gdf = gdf[gdf.geometry.type.isin(sorted(geometry_types))].copy()
    return gdf