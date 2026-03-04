import logging
import geopandas as gpd

logger = logging.getLogger(__name__)


def filter_buildings_by_area(gdf: gpd.GeoDataFrame, min_area_m2: float = 9.0) -> gpd.GeoDataFrame:
    """
    Filtre les bâtiments dont l'emprise au sol est strictement inférieure au seuil (ex: 9m2).

    Args:
        gdf (gpd.GeoDataFrame): Les bâtiments à filtrer (doit être dans un CRS métrique, ex: EPSG:2154).
        min_area_m2 (float): La surface minimale en mètres carrés.

    Returns:
        gpd.GeoDataFrame: Les bâtiments filtrés.
    """
    logger.info(f"Filtrage géométrique : suppression des polygones < {min_area_m2}m²...")

    # Calcul de la surface si elle n'existe pas déjà
    if 'surface_sol' not in gdf.columns:
        gdf['surface_sol'] = gdf.geometry.area

    # Filtrage
    initial_count = len(gdf)
    gdf_filtered = gdf[gdf['surface_sol'] >= min_area_m2].copy()
    filtered_count = len(gdf_filtered)

    logger.info(
        f"Filtrage terminé : {initial_count - filtered_count} bâtiments supprimés. Reste {filtered_count} entités.")
    return gdf_filtered


def compute_centroids(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """
    Calcule le centroïde de chaque polygone. Ce point servira pour la jointure
    spatiale (Point-in-Polygon) avec le carroyage INSEE.

    Args:
        gdf (gpd.GeoDataFrame): GeoDataFrame contenant des polygones.

    Returns:
        gpd.GeoDataFrame: Le même GeoDataFrame enrichi d'une colonne 'centroid'.
    """
    logger.info("Calcul des centroïdes des bâtiments...")
    # On stocke le centroïde dans une nouvelle colonne pour ne pas écraser le polygone original (on en aura besoin plus tard)
    gdf['centroid'] = gdf.geometry.centroid
    return gdf