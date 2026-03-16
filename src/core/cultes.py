"""
Identification locale des lieux de culte.

Le projet privilégie ici la sémantique déjà présente dans la BD TOPO pour
rester hors ligne et reproductible, sans requêtes OSM dynamiques au moment de
l'exécution du pipeline principal.
"""

import logging
import geopandas as gpd

logger = logging.getLogger(__name__)


def integrer_lieux_culte(gdf_batiments: gpd.GeoDataFrame, config: dict) -> gpd.GeoDataFrame:
    """
    Identifie les lieux de culte directement dans la BD TOPO.

    Ce choix évite une dépendance réseau et garantit que le même jeu d'entrée
    produira toujours les mêmes bâtiments de culte.

    Returns
    -------
    geopandas.GeoDataFrame
        Bâtiments enrichis de `is_culte` et `nom_culte`.
    """
    logger.info("Intégration spatiale des lieux de culte depuis la BD TOPO...")

    df = gdf_batiments.copy()

    # 1. Initialisation des attributs
    df['is_culte'] = False
    df['nom_culte'] = "None"

    # La BD TOPO expose déjà des indices sémantiques suffisants pour le culte.
    usage_culte = df['usage_1'].fillna("").str.contains('Religieux', case=False, na=False)
    nature_culte = df['nature'].fillna("").str.contains('Eglise|Chapelle', case=False, na=False)
    mask_culte = usage_culte | nature_culte

    df.loc[mask_culte, 'is_culte'] = True
    df.loc[mask_culte, 'nom_culte'] = df.loc[mask_culte, 'nature'].fillna("Lieu de culte")

    logger.info(f"Terminé : {int(mask_culte.sum())} bâtiments identifiés comme lieux de culte.")
    return df
