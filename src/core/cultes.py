"""
Identification locale des lieux de culte.

Le projet privilégie ici la sémantique déjà présente dans la BD TOPO pour
rester hors ligne et reproductible, sans requêtes OSM dynamiques au moment de
l'exécution du pipeline principal.
"""

import logging
import geopandas as gpd

logger = logging.getLogger(__name__)


def _culte_household_exception_patterns(config: dict) -> list[str]:
    raw_patterns = (
        config.get('demographics', {})
        .get('households', {})
        .get('culte_residential_exceptions_any_of', ['presbytère', 'presbytere'])
    )
    return [str(pattern).casefold() for pattern in raw_patterns if str(pattern).strip()]


def _has_culte_household_exception(row, patterns: list[str]) -> bool:
    if not patterns:
        return False
    values = [
        str(row.get('nature', '') or '').casefold(),
        str(row.get('usage_1', '') or '').casefold(),
        str(row.get('nom_culte', '') or '').casefold(),
    ]
    return any(pattern in value for pattern in patterns for value in values)


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
    df['culte_household_allowed'] = True

    # La BD TOPO expose déjà des indices sémantiques suffisants pour le culte.
    usage_culte = df['usage_1'].fillna("").str.contains('Religieux', case=False, na=False)
    nature_culte = df['nature'].fillna("").str.contains('Eglise|Chapelle', case=False, na=False)
    mask_culte = usage_culte | nature_culte

    df.loc[mask_culte, 'is_culte'] = True
    df.loc[mask_culte, 'nom_culte'] = df.loc[mask_culte, 'nature'].fillna("Lieu de culte")
    df.loc[mask_culte, 'culte_household_allowed'] = False

    exception_patterns = _culte_household_exception_patterns(config)
    if exception_patterns:
        exception_mask = df.apply(_has_culte_household_exception, axis=1, args=(exception_patterns,))
        df.loc[mask_culte & exception_mask, 'culte_household_allowed'] = True

    logger.info(f"Terminé : {int(mask_culte.sum())} bâtiments identifiés comme lieux de culte.")
    return df
