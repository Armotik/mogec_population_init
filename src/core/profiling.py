import logging
import geopandas as gpd
logger = logging.getLogger(__name__)


def generer_profils_batiments(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """
    Calcule les probabilités sociodémographiques pour chaque bâtiment
    en fonction des données du carreau INSEE associé.
    """
    logger.info("Calcul des profils sociodémographiques (Profiling)...")

    # On travaille sur une copie pour éviter les warnings
    df = gdf.copy()

    # 1. Calcul des ratios d'âge (Basé sur la population totale 'ind')
    # Ces colonnes nous permettront dans GAMA de faire :
    # if(flip(prob_senior)) { create agent_senior; }

    df['prob_enfant'] = (df['ind_0_3'] + df['ind_4_5'] + df['ind_6_10'] + df['ind_11_17']) / df['ind']
    df['prob_adulte'] = (df['ind_18_24'] + df['ind_25_39'] + df['ind_40_54'] + df['ind_55_64']) / df['ind']
    df['prob_senior'] = (df['ind_65_79'] + df['ind_80p']) / df['ind']

    # 2. Calcul des types de ménages (Basé sur le nombre de ménages 'men')
    df['prob_menage_1ind'] = df['men_1ind'] / df['men']
    df['prob_menage_famille'] = (df['men_fmp']) / df['men']  # Familles monoparentales

    # 3. Revenus et Pauvreté (Indice de vulnérabilité sociale)
    df['prob_pauvrete'] = df['men_pauv'] / df['men']

    # Nettoyage des valeurs aberrantes (NaN ou > 1 dues aux secrets statistiques)
    cols_prob = ['prob_enfant', 'prob_adulte', 'prob_senior', 'prob_menage_1ind', 'prob_menage_famille',
                 'prob_pauvrete']
    for col in cols_prob:
        df[col] = df[col].fillna(df[col].mean()).clip(0, 1)

    logger.info("Profiling terminé : les bâtiments sont enrichis de probabilités comportementales.")
    return df