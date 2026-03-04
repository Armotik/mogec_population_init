import logging
from pathlib import Path
import geopandas as gpd
import osmnx as ox

logger = logging.getLogger(__name__)


def get_study_area_boundary(commune_name: str, target_crs: int = 2154, buffer_m: int = 0) -> gpd.GeoDataFrame:
    """
    Récupère le polygone des frontières administratives d'une commune via OpenStreetMap,
    avec la possibilité d'appliquer une zone tampon (buffer) pour éviter les effets de bord.
    """
    logger.info(f"Récupération des limites administratives pour : {commune_name}")
    try:
        # 1. Extraction OSM (WGS84 - EPSG:4326)
        boundary = ox.geocode_to_gdf(commune_name)

        # 2. Reprojection en Lambert 93 (métrique)
        boundary = boundary.to_crs(epsg=target_crs)

        # 3. Application du Buffer (si demandé)
        if buffer_m > 0:
            logger.info(f"Application d'un buffer de {buffer_m} mètres pour absorber l'effet de bord...")
            # On remplace la géométrie stricte par la géométrie dilatée
            boundary['geometry'] = boundary.geometry.buffer(buffer_m)

        logger.info(f"Frontières prêtes (EPSG:{target_crs}).")
        return boundary

    except Exception as e:
        logger.error(f"Erreur lors de la récupération des limites de {commune_name}: {e}")
        raise


def load_geopackage_with_mask(file_path: str, layer_name: str, mask_gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """
    Charge une couche spécifique d'un GeoPackage en filtrant spatialement à la lecture.
    """
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"Fichier introuvable : {file_path}")

    logger.info(f"Chargement de la couche '{layer_name}' depuis {path.name} avec masque spatial...")

    try:
        gdf = gpd.read_file(path, layer=layer_name, mask=mask_gdf)
        logger.info(f"Succès : {len(gdf)} entités chargées depuis {path.name}.")
        return gdf
    except Exception as e:
        logger.error(f"Erreur lors du chargement de {file_path}: {e}")
        raise


def fetch_osm_pois(boundary_gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """
    Télécharge dynamiquement les Points d'Intérêt (POI) commerciaux et touristiques depuis OSM.
    """
    logger.info("Interrogation de l'API OpenStreetMap pour les POIs...")
    boundary_wgs84 = boundary_gdf.to_crs(epsg=4326)
    polygon_wgs84 = boundary_wgs84.geometry.iloc[0]

    tags = {
        'tourism': ['hotel', 'camp_site', 'chalet', 'guest_house', 'hostel', 'motel'],
        'amenity': ['restaurant', 'cafe', 'bar', 'fast_food', 'pub', 'marketplace'],
        'natural': ['beach']
    }

    try:
        pois = ox.features_from_polygon(polygon_wgs84, tags=tags)
        pois = pois[pois.geometry.type.isin(['Polygon', 'MultiPolygon'])]
        pois = pois.to_crs(boundary_gdf.crs)
        logger.info(f"Succès : {len(pois)} POIs pertinents téléchargés depuis OSM.")
        return pois
    except Exception as e:
        logger.error(f"Erreur lors de la récupération des POIs OSM: {e}")
        raise