"""
Export des données finales vers les formats consommés par GAMA.

Le choix actuel est un GeoPackage unique contenant les attributs bâtimentaires,
les indicateurs de profil, les POI et la matrice horaire complète.
"""

import logging
from pathlib import Path
import geopandas as gpd

logger = logging.getLogger(__name__)


def exporter_pour_gama(gdf: gpd.GeoDataFrame, config: dict):
    """
    Prépare et sauvegarde le GeoDataFrame final pour GAMA,
    incluant la matrice de présence horaire.

    Le module ne fait pas qu'écrire sur disque : il sélectionne aussi les
    colonnes jugées utiles pour la simulation et l'audit scientifique.
    """
    output_path = Path(config['data_paths']['output']['final_export'])
    output_path.parent.mkdir(parents=True, exist_ok=True)

    logger.info(f"Préparation de l'export final vers {output_path}...")

    df_export = gdf.copy()

    # On définit les colonnes de base
    cols_a_garder = [
        'geometry', 'building_id', 'building_id_source', 'usage_1', 'nature', 'hauteur', 'pop_t0', 'dest_id',
        'prob_senior', 'prob_enfant', 'prob_pauvrete',
        'n_scolaire', 'n_senior', 'n_actif_local', 'n_actif_navetteur', 'n_households',
        'pop_nonres_accommodation', 'pop_nonres_activity',
        'accommodation_capacity_raw', 'accommodation_capacity_retained',
        'accommodation_source_types', 'accommodation_offer_names',
        'accommodation_overlap_risk', 'accommodation_overlap_action',
        'exogenous_zone_type', 'beach_capacity',
        'is_restaurant', 'nom_resto', 'horaires_osm', 'horaires_source', 'restaurant_service_slots',
        'is_culte', 'nom_culte'
    ]

    # On ajoute dynamiquement les 24 colonnes horaires
    colonnes_heures = [f'pop_h{h}' for h in range(24)]
    cols_a_garder.extend(colonnes_heures)
    df_export['scenario_name'] = config['scenario']['name']
    df_export['day_of_week'] = config['scenario']['day_of_week']
    df_export['random_seed'] = int(config['project']['random_seed'])
    cols_a_garder.extend(['scenario_name', 'day_of_week', 'random_seed'])

    # Nettoyage des types pour GAMA
    if 'dest_id' in df_export.columns:
        df_export['dest_id'] = df_export['dest_id'].astype(str)

    # Filtrage strict sur les colonnes existantes pour éviter les erreurs
    cols_finales = [c for c in cols_a_garder if c in df_export.columns]
    df_export = df_export[cols_finales]

    # Sauvegarde
    df_export.to_file(output_path, driver="GPKG")

    logger.info(f"Export terminé : {len(df_export)} bâtiments prêts pour GAMA avec cycle 24h.")
    return output_path
