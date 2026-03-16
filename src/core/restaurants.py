"""
Intégration des restaurants dans le référentiel bâtimentaire.

Le module relie un audit CSV issu d'OSM à la BD TOPO, impute si besoin des
plages de service plausibles et expose des attributs directement exploitables
par la matrice horaire et par l'export GAMA.
"""

import logging
import pandas as pd
import geopandas as gpd
from shapely.geometry import Point
from pathlib import Path
import numpy as np

from src.core.randomness import build_rng

logger = logging.getLogger(__name__)


def _normaliser_heure(value, fallback: str) -> str:
    """
    Normalise une heure de service au format HH:MM.

    Tout format invalide ou manquant est remplacé par une valeur de repli.
    """
    if pd.isna(value) or value in [None, "", "None"]:
        return fallback
    parsed = pd.to_datetime(str(value), format="%H:%M", errors="coerce")
    if pd.isna(parsed):
        return fallback
    return parsed.strftime("%H:%M")


def _imputer_horaires_restaurant(row: pd.Series, rng: np.random.Generator) -> tuple[str, str, str]:
    """
    Impute des horaires plausibles quand OSM ne fournit pas l'information.

    Le tirage reste strictement reproductible car il dépend du générateur
    déterministe dérivé du seed projet.

    Returns
    -------
    tuple[str, str, str]
        Heure d'ouverture, heure de fermeture, provenance de l'information.
    """
    ouverture = row.get('horaire_ouverture')
    fermeture = row.get('horaire_fermeture')

    if pd.notna(ouverture) and pd.notna(fermeture):
        return _normaliser_heure(ouverture, "12:00"), _normaliser_heure(fermeture, "22:00"), "audit_csv"

    profils = [
        ("11:30", "14:30", "18:30", "22:00"),
        ("12:00", "14:00", "19:00", "22:30"),
        ("12:00", "15:00", "19:00", "23:00"),
    ]
    profile = profils[int(rng.integers(0, len(profils)))]
    horaires_concat = f"{profile[0]}-{profile[1]};{profile[2]}-{profile[3]}"
    return profile[0], profile[3], f"imputed:{horaires_concat}"


def _restaurant_est_ouvert(row: pd.Series, hour: int) -> bool:
    """
    Indique si un restaurant est ouvert pour une heure entière donnée.

    Les plages sont stockées sous forme compacte "HH:MM-HH:MM;HH:MM-HH:MM".
    """
    if not bool(row.get('is_restaurant', False)):
        return False

    plages = str(row.get('restaurant_service_slots', '')).split(';')
    for plage in plages:
        if not plage or '-' not in plage:
            continue
        debut, fin = plage.split('-', 1)
        debut_h = int(debut.split(':')[0])
        fin_h = int(fin.split(':')[0])
        if debut_h <= hour <= fin_h:
            return True
    return False


def restaurants_ouverts_a_l_heure(gdf_batiments: gpd.GeoDataFrame, hour: int) -> list[int]:
    """
    Retourne les identifiants des bâtiments restaurant ouverts à une heure donnée.

    Cette fonction évite d'envoyer des agents dans des POI fermés.
    """
    if 'is_restaurant' not in gdf_batiments.columns:
        return []
    mask = gdf_batiments.apply(lambda row: _restaurant_est_ouvert(row, hour), axis=1)
    return gdf_batiments.loc[mask, 'building_id'].astype(str).tolist()


def integrer_restaurants_aux_batiments(gdf_batiments: gpd.GeoDataFrame, config: dict) -> gpd.GeoDataFrame:
    """
    Associe les restaurants du CSV OSM aux bâtiments de la BD TOPO.
    Prépare les attributs nécessaires pour l'initialisation des agents dans GAMA.

    Returns
    -------
    geopandas.GeoDataFrame
        Bâtiments enrichis des colonnes `is_restaurant`, `nom_resto`,
        `horaires_osm`, `horaires_source` et `restaurant_service_slots`.
    """
    logger.info("Intégration spatiale des restaurants OSM aux bâtiments...")

    df = gdf_batiments.copy()

    # 1. Initialisation des nouvelles colonnes pour tous les bâtiments
    df['is_restaurant'] = False
    df['nom_resto'] = "None"
    df['horaires_osm'] = "None"
    df['horaires_source'] = "none"
    df['restaurant_service_slots'] = ""
    rng = build_rng(config, "restaurants")
    matching_cfg = config.get('poi_matching', {}).get('restaurants', {})
    max_distance_m = float(matching_cfg.get('max_distance_m', 20.0))
    preferred_usage = matching_cfg.get('preferred_usage_any_of', [])
    allow_fallback_any_usage = bool(matching_cfg.get('allow_fallback_any_usage', True))
    concat_multiple_names = bool(matching_cfg.get('concat_multiple_names', True))

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
        horaire_ouverture, horaire_fermeture, source_horaires = _imputer_horaires_restaurant(resto, rng)

        if str(source_horaires).startswith("imputed:"):
            service_slots = source_horaires.split(":", 1)[1]
        else:
            service_slots = f"{horaire_ouverture}-{horaire_fermeture}"

        point_mask = df.geometry.intersects(resto.geometry)
        point_candidates = df[point_mask].copy()

        if point_candidates.empty:
            distances = df.geometry.distance(resto.geometry)
            radius_candidates = df[distances <= max_distance_m].copy()
            radius_candidates['distance_to_poi'] = distances.loc[radius_candidates.index]
        else:
            radius_candidates = point_candidates.copy()
            radius_candidates['distance_to_poi'] = 0.0

        if radius_candidates.empty:
            continue

        if preferred_usage:
            preferred_mask = radius_candidates['usage_1'].fillna("").apply(
                lambda usage: any(pattern.casefold() in str(usage).casefold() for pattern in preferred_usage)
            )
            preferred_candidates = radius_candidates[preferred_mask].copy()
        else:
            preferred_candidates = radius_candidates

        if not preferred_candidates.empty:
            candidate_pool = preferred_candidates
        elif allow_fallback_any_usage:
            candidate_pool = radius_candidates
        else:
            continue

        batiment_id_proche = candidate_pool.sort_values('distance_to_poi').index[0]
        existing_name = str(df.at[batiment_id_proche, 'nom_resto'])
        new_name = str(resto['nom'])

        df.at[batiment_id_proche, 'is_restaurant'] = True
        if concat_multiple_names and existing_name not in {"None", "", new_name}:
            df.at[batiment_id_proche, 'nom_resto'] = f"{existing_name} | {new_name}"
        else:
            df.at[batiment_id_proche, 'nom_resto'] = new_name if existing_name in {"None", ""} else existing_name
        df.at[batiment_id_proche, 'horaires_osm'] = str(resto['opening_hours_brut'])
        df.at[batiment_id_proche, 'horaires_source'] = source_horaires
        df.at[batiment_id_proche, 'restaurant_service_slots'] = service_slots

    n_restos_integres = df['is_restaurant'].sum()
    logger.info(f"{n_restos_integres} bâtiments ont été identifiés comme restaurants.")

    return df
