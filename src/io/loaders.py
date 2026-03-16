"""
Chargement des données d'entrée spatiales et administratives.

Ce module regroupe les utilitaires de lecture du référentiel de frontière, des
couches GeoPackage masquées spatialement et, en second choix, quelques accès
dynamiques à OSM quand une source locale n'est pas fournie.
"""

import logging
from pathlib import Path
import geopandas as gpd
import osmnx as ox

logger = logging.getLogger(__name__)


def get_study_area_boundary(commune_name: str, target_crs: int = 2154, buffer_m: int = 0) -> gpd.GeoDataFrame:
    """
    Récupère le polygone des frontières administratives d'une commune via OpenStreetMap,
    avec la possibilité d'appliquer une zone tampon (buffer) pour éviter les effets de bord.

    Cette fonction reste disponible comme repli, mais le pipeline principal
    préfère désormais `load_study_area_boundary` avec une source locale.
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


def load_study_area_boundary(config: dict, strict: bool = False) -> gpd.GeoDataFrame:
    """
    Charge la frontière d'étude depuis une source locale si elle est configurée.

    Pour un travail de recherche, cette source locale est prioritaire car elle
    fige le référentiel administratif utilisé par toutes les exécutions.

    Parameters
    ----------
    config:
        Configuration projet.
    strict:
        Si vrai, ne pas appliquer le buffer de lecture.
    """
    study_area = config['study_area']
    target_crs = config['project']['crs_epsg']
    buffer_m = 0 if strict else study_area.get('buffer_m', 0)
    boundary_path = study_area.get('boundary_path')

    if boundary_path:
        path = Path(boundary_path)
        if not path.exists():
            raise FileNotFoundError(f"Fichier de frontière introuvable : {boundary_path}")

        boundary_layer = study_area.get('boundary_layer', 'commune')
        boundary_name_field = study_area.get('boundary_name_field', 'libelle_commune')
        boundary_name_value = study_area.get('boundary_name_value') or study_area['commune_name'].split(",")[0].strip()

        logger.info(f"Chargement de la frontière locale '{boundary_name_value}' depuis {path.name}...")
        boundary = gpd.read_file(path, layer=boundary_layer)
        mask = boundary[boundary_name_field].fillna("").str.casefold() == boundary_name_value.casefold()
        boundary = boundary.loc[mask].copy()

        if boundary.empty:
            raise ValueError(
                f"Aucune entité trouvée pour '{boundary_name_value}' dans {boundary_layer}.{boundary_name_field}"
            )

        boundary = boundary.to_crs(epsg=target_crs)
        if buffer_m > 0:
            boundary['geometry'] = boundary.geometry.buffer(buffer_m)
        return boundary

    return get_study_area_boundary(study_area['commune_name'], target_crs, buffer_m=buffer_m)


def load_geopackage_with_mask(file_path: str, layer_name: str, mask_gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """
    Charge une couche spécifique d'un GeoPackage en filtrant spatialement à la lecture.

    Le paramètre `mask` permet de limiter dès l'I/O les entités chargées,
    ce qui évite de lire la totalité d'une couche départementale ou nationale.
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

    Cette fonction n'est pas utilisée dans le pipeline reproductible principal,
    mais reste utile pour des explorations complémentaires.
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
