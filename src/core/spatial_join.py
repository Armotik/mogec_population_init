"""
Jointure spatiale entre bâtiments et carroyage INSEE.

Le rôle de ce module est d'associer à chaque bâtiment les variables du carreau
Filosofi dans lequel tombe son centroïde, afin de rendre possible la
ventilation ultérieure de la population agrégée.
"""

import logging
import geopandas as gpd

logger = logging.getLogger(__name__)


def join_buildings_to_grid(bati_gdf: gpd.GeoDataFrame, grid_gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """
    Assigne chaque bâtiment à son carreau INSEE via son centroïde.

    Parameters
    ----------
    bati_gdf:
        Bâtiments contenant une colonne `centroid`.
    grid_gdf:
        Carroyage INSEE/Filosofi avec variables démographiques.

    Returns
    -------
    geopandas.GeoDataFrame
        Bâtiments enrichis des attributs de leur carreau d'appartenance.
    """
    logger.info("Début de la jointure spatiale (Bâtiments -> Carroyage INSEE)...")

    # 1. Vérification stricte des systèmes de projection (CRS)
    if bati_gdf.crs != grid_gdf.crs:
        logger.warning(f"Reprojection du carroyage de {grid_gdf.crs} vers {bati_gdf.crs}...")
        grid_gdf = grid_gdf.to_crs(bati_gdf.crs)

    # 2. L'astuce géomatique : On change temporairement la géométrie active pour utiliser le point
    bati_gdf = bati_gdf.set_geometry('centroid')

    # 3. La jointure (Inner Join : on ne garde que les bâtiments qui sont dans un carreau)
    jointure = gpd.sjoin(bati_gdf, grid_gdf, how='inner', predicate='within')

    # 4. On restaure le polygone du bâtiment comme géométrie principale (pour GAMA plus tard)
    jointure = jointure.set_geometry('geometry')

    # Nettoyage de la colonne technique d'index générée par sjoin
    if 'index_right' in jointure.columns:
        jointure = jointure.drop(columns=['index_right'])

    logger.info(f"Jointure terminée : {len(jointure)} bâtiments ont été associés à un carreau INSEE.")
    return jointure
