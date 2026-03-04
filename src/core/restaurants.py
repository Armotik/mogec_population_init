import logging
import pandas as pd
import geopandas as gpd
from shapely.geometry import Point
from pathlib import Path

logger = logging.getLogger(__name__)


def integrer_restaurants_aux_batiments(gdf_batiments: gpd.GeoDataFrame, config: dict) -> gpd.GeoDataFrame:
    """
    Associe les restaurants du CSV OSM aux bâtiments de la BD TOPO.
    Prépare les attributs nécessaires pour l'initialisation des agents dans GAMA.
    """
    logger.info("Intégration spatiale des restaurants OSM aux bâtiments...")

    df = gdf_batiments.copy()

    # 1. Initialisation des nouvelles colonnes pour tous les bâtiments
    df['is_restaurant'] = False
    df['nom_resto'] = "None"
    df['horaires_osm'] = "None"

    chemin_csv = Path(config['data_paths']['input'].get('audit_restaurants', 'data/01_raw/audit_restaurants_batz.csv'))

    if not chemin_csv.exists():
        logger.warning(f"Fichier restaurant introuvable : {chemin_csv}. Les bâtiments n'auront pas de restaurants.")
        return df

    # 2. Chargement et spatialisation des points OSM
    df_restos = pd.read_csv(chemin_csv, sep=';')
    geometry = [Point(xy) for xy in zip(df_restos['lon'], df_restos['lat'])]
    gdf_restos = gpd.GeoDataFrame(df_restos, geometry=geometry, crs="EPSG:4326")

    # Reprojection dans le même système de coordonnées que les bâtiments (Lambert 93)
    gdf_restos = gdf_restos.to_crs(df.crs)

    # 3. Jointure Spatiale : Assigner chaque point au bâtiment le plus proche
    # Pour garantir les performances, on boucle sur les restaurants (il y en a peu)
    for index, resto in gdf_restos.iterrows():
        # Calcul de la distance entre ce restaurant et tous les bâtiments
        distances = df.geometry.distance(resto.geometry)

        # Identification du bâtiment le plus proche
        batiment_id_proche = distances.idxmin()
        distance_min = distances.min()

        # Tolérance de 20 mètres (utile si le point OSM est sur le trottoir devant le bâtiment)
        if distance_min <= 20.0:
            df.at[batiment_id_proche, 'is_restaurant'] = True
            df.at[batiment_id_proche, 'nom_resto'] = str(resto['nom'])
            df.at[batiment_id_proche, 'horaires_osm'] = str(resto['opening_hours_brut'])

    n_restos_integres = df['is_restaurant'].sum()
    logger.info(f"{n_restos_integres} bâtiments ont été identifiés comme restaurants.")

    return df