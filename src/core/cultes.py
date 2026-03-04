import logging
import pandas as pd
import geopandas as gpd
import osmnx as ox

logger = logging.getLogger(__name__)


def integrer_lieux_culte(gdf_batiments: gpd.GeoDataFrame, config: dict) -> gpd.GeoDataFrame:
    """
    Identifie les lieux de culte via OSMnx et les associe aux bâtiments de la BD TOPO.
    Utile pour modéliser les pics de concentration événementiels (ex: messe du dimanche).
    """
    logger.info("Intégration spatiale des lieux de culte (OSM) aux bâtiments...")

    df = gdf_batiments.copy()

    # 1. Initialisation des attributs
    df['is_culte'] = False
    df['nom_culte'] = "None"

    commune_name = config['study_area']['commune_name']
    tags_culte = {'amenity': 'place_of_worship'}

    # 2. Récupération des données OSM
    try:
        gdf_osm_culte = ox.features_from_place(commune_name, tags=tags_culte)
        if gdf_osm_culte.empty:
            logger.warning("Aucun lieu de culte trouvé sur OSM pour cette commune.")
            return df
    except Exception as e:
        logger.error(f"Échec de la requête OSMnx pour les lieux de culte : {e}")
        return df

    # Reprojection en Lambert 93 (EPSG:2154) pour correspondre aux bâtiments
    gdf_osm_culte = gdf_osm_culte.to_crs(df.crs)

    # 3. Jointure spatiale
    n_cultes = 0
    for index, lieu in gdf_osm_culte.iterrows():
        nom = lieu.get('name', 'Culte Inconnu')
        if pd.isna(nom):
            nom = 'Culte Inconnu'

        # CORRECTION DU WARNING SHAPELY : Utilisation de geom_type au lieu de type
        centroid = lieu.geometry.centroid if not lieu.geometry.geom_type == 'Point' else lieu.geometry

        # Calcul des distances vers tous les bâtiments
        distances = df.geometry.distance(centroid)
        batiment_id_proche = distances.idxmin()
        distance_min = distances.min()

        # Tolérance de 20m
        if distance_min <= 20.0:
            df.at[batiment_id_proche, 'is_culte'] = True
            df.at[batiment_id_proche, 'nom_culte'] = str(nom)
            n_cultes += 1
            logger.info(f"Lieu de culte lié : {nom}")

    logger.info(f"Terminé : {n_cultes} bâtiments identifiés comme lieux de culte.")
    return df