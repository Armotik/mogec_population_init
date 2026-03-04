import logging
import geopandas as gpd

logger = logging.getLogger(__name__)


def clip_to_strict_boundary(gdf: gpd.GeoDataFrame, strict_boundary_gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """
    Supprime les bâtiments situés dans la zone tampon (buffer) pour ne garder
    que ceux à l'intérieur des limites administratives réelles.
    """
    logger.info("Découpage final : suppression des bâtiments hors limites administratives...")

    initial_count = len(gdf)
    initial_pop = gdf['pop_t0'].sum()

    # On utilise sjoin pour ne garder que ce qui est à l'intérieur (within) du polygone strict
    # On se base sur le centroïde pour éviter qu'un bâtiment à cheval sur la limite soit coupé en deux
    gdf_centroids = gdf.copy().set_geometry('centroid')

    # Jointure spatiale "inner" pour filtrer
    gdf_cleaned = gpd.sjoin(gdf_centroids, strict_boundary_gdf, how='inner', predicate='within')

    # On restaure la géométrie polygonale pour l'export
    gdf_cleaned = gdf_cleaned.set_geometry('geometry')

    # Nettoyage des colonnes de jointure inutiles
    columns_to_drop = [col for col in gdf_cleaned.columns if 'index_right' in col or 'left' in col]
    gdf_cleaned = gdf_cleaned.drop(columns=columns_to_drop)

    final_count = len(gdf_cleaned)
    final_pop = gdf_cleaned['pop_t0'].sum()

    logger.info(f"Nettoyage terminé : {initial_count - final_count} bâtiments supprimés.")
    logger.info(f"Population finale retenue pour la simulation : {final_pop} agents.")

    return gdf_cleaned