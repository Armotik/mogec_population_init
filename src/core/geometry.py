"""
Briques de préparation géométrique des bâtiments.

Ce module intervient très tôt dans le pipeline : il filtre les emprises non
pertinentes pour l'habitat puis calcule les centroïdes utilisés pour les
jointures spatiales avec le carroyage INSEE et les limites communales.
"""

import logging
import geopandas as gpd

logger = logging.getLogger(__name__)


def filter_buildings_by_area(gdf: gpd.GeoDataFrame, min_area_m2: float = 9.0) -> gpd.GeoDataFrame:
    """
    Filtre les bâtiments dont l'emprise au sol est strictement inférieure au seuil (ex: 9m2).

    Parameters
    ----------
    gdf:
        Bâtiments à filtrer, idéalement déjà projetés dans un CRS métrique.
    min_area_m2:
        Surface minimale conservée. Les entités plus petites sont considérées
        comme trop petites pour représenter des lieux de présence crédibles.

    Returns
    -------
    geopandas.GeoDataFrame
        Sous-ensemble filtré, enrichi de `surface_sol` si nécessaire.
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

    Parameters
    ----------
    gdf:
        GeoDataFrame contenant des géométries surfaciques.

    Returns
    -------
    geopandas.GeoDataFrame
        Même table, avec une colonne `centroid` conservant la trace des points
        sans écraser la géométrie polygonale d'origine.
    """
    logger.info("Calcul des centroïdes des bâtiments...")
    # On stocke le centroïde dans une nouvelle colonne pour ne pas écraser le polygone original (on en aura besoin plus tard)
    gdf['centroid'] = gdf.geometry.centroid
    return gdf
