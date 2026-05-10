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


def _boundary_name_value(study_area: dict) -> str:
    configured_value = study_area.get('boundary_name_value')
    if configured_value:
        return str(configured_value)
    return study_area['commune_name'].split(",")[0].strip()


def _apply_boundary_buffer(boundary: gpd.GeoDataFrame, buffer_m: int) -> gpd.GeoDataFrame:
    if buffer_m <= 0:
        return boundary
    boundary = boundary.copy()
    boundary['geometry'] = boundary.geometry.buffer(buffer_m)
    return boundary


def _load_local_boundary(study_area: dict, target_crs: int, buffer_m: int) -> gpd.GeoDataFrame | None:
    boundary_path = study_area.get('boundary_path')
    if not boundary_path:
        return None

    path = Path(boundary_path)
    if not path.exists():
        logger.warning(
            "Fichier de frontière introuvable : %s ; repli vers le geocodage OSM.",
            boundary_path,
        )
        return None

    boundary_layer = study_area.get('boundary_layer', 'commune')
    boundary_name_field = study_area.get('boundary_name_field', 'libelle_commune')
    boundary_name_value = _boundary_name_value(study_area)

    logger.info(f"Chargement de la frontière locale '{boundary_name_value}' depuis {path.name}...")
    boundary = gpd.read_file(path, layer=boundary_layer)
    mask = boundary[boundary_name_field].fillna("").str.casefold() == boundary_name_value.casefold()
    boundary = boundary.loc[mask].copy()

    if boundary.empty:
        logger.warning(
            "Aucune entité trouvée pour '%s' dans %s.%s ; repli vers le geocodage OSM.",
            boundary_name_value,
            boundary_layer,
            boundary_name_field,
        )
        return None

    boundary = boundary.to_crs(epsg=target_crs)
    return _apply_boundary_buffer(boundary, buffer_m)


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
    allow_network_fallback = bool(study_area.get('allow_network_fallback', False))
    local_boundary = _load_local_boundary(study_area, target_crs, buffer_m)
    if local_boundary is not None:
        return local_boundary
    if not allow_network_fallback:
        boundary_path = study_area.get('boundary_path', '<non configure>')
        raise FileNotFoundError(
            "Frontiere locale indisponible et fallback OSM interdit "
            f"(study_area.allow_network_fallback=false). Chemin: {boundary_path}"
        )
    return get_study_area_boundary(study_area['commune_name'], target_crs, buffer_m=buffer_m)


def _validate_mask(mask_gdf: gpd.GeoDataFrame) -> None:
    if mask_gdf.empty:
        raise ValueError("Le masque spatial fourni est vide.")
    if mask_gdf.crs is None:
        raise ValueError("Le masque spatial doit avoir un CRS défini.")


def load_geopackage_with_mask(file_path: str, layer_name: str, mask_gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """
    Charge une couche spécifique d'un GeoPackage en filtrant spatialement à la lecture.

    Le paramètre `mask` permet de limiter dès l'I/O les entités chargées,
    ce qui évite de lire la totalité d'une couche départementale ou nationale.
    """
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"Fichier introuvable : {file_path}")
    _validate_mask(mask_gdf)

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
