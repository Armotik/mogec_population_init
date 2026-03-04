import logging
from pathlib import Path
import geopandas as gpd

logger = logging.getLogger(__name__)


def exporter_pour_gama(gdf: gpd.GeoDataFrame, config: dict):
    """
    Prépare et sauvegarde le GeoDataFrame final pour GAMA,
    incluant la matrice de présence horaire.
    """
    output_path = Path(config['data_paths']['output']['final_export'])
    output_path.parent.mkdir(parents=True, exist_ok=True)

    logger.info(f"Préparation de l'export final vers {output_path}...")

    df_export = gdf.copy()

    # On définit les colonnes de base
    cols_a_garder = [
        'geometry', 'usage_1', 'hauteur', 'dest_id',
        'prob_senior', 'prob_enfant', 'prob_pauvrete'
    ]

    # On ajoute dynamiquement les 24 colonnes horaires
    colonnes_heures = [f'pop_h{h}' for h in range(24)]
    cols_a_garder.extend(colonnes_heures)

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