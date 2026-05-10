"""
Ventilation résidentielle de la population à l'échelle du bâtiment.

Cette brique traduit une population agrégée par carreau en effectifs par
bâtiment résidentiel, à partir d'un indicateur de capacité et d'un correctif
saisonnier sur les résidences secondaires.
"""

import logging
import pandas as pd
import geopandas as gpd
import numpy as np
import math

logger = logging.getLogger(__name__)


def calculer_capacite_residentielle(row, fallback_sqm: float) -> float:
    """
    Calcule l'indice de capacité d'un bâtiment (Priorité au nombre de logements).
    Si l'info est manquante, on estime via la surface au sol et la hauteur.

    La capacité retournée n'est pas un nombre d'habitants mais un poids
    relatif utilisé pour partager la population du carreau entre plusieurs
    bâtiments résidentiels.
    """
    if pd.notna(row.get('nombre_de_logements')) and row['nombre_de_logements'] > 0:
        return float(row['nombre_de_logements'])

    hauteur = row.get('hauteur', 5.0)
    if pd.isna(hauteur):
        hauteur = 5.0

    surface = row.get('surface_sol', 0.0)

    etages_estimes = max(0, math.floor((hauteur - 5) / 3))
    volume_index = surface * (1 + etages_estimes)

    capacite_estimee = max(1, round(volume_index / fallback_sqm))
    return float(capacite_estimee)


def _target_population_for_carreau(group: pd.DataFrame, modulateur_temporel: float) -> int:
    ind_values = group['ind'].dropna()
    if ind_values.empty:
        return 0
    return int(round(float(ind_values.iloc[0]) * modulateur_temporel))


def _redistribute_missing_population(
    gdf: gpd.GeoDataFrame,
    eligible_mask: pd.Series,
    missing_population: int,
) -> gpd.GeoDataFrame:
    if missing_population <= 0:
        return gdf

    pool = gdf.loc[eligible_mask, 'capacite_logts'].fillna(0.0).astype(float)
    total_capacity = float(pool.sum())
    if pool.empty or total_capacity <= 0:
        raise ValueError(
            "Aucune capacite residentielle eligible pour redistribuer la population exclue des batiments de culte."
        )

    weighted = (missing_population * pool / total_capacity)
    base_allocation = np.floor(weighted).astype(int)
    remainder = int(missing_population - int(base_allocation.sum()))
    if remainder > 0:
        extra_indices = (weighted - base_allocation).nlargest(remainder).index
        base_allocation.loc[extra_indices] += 1

    gdf.loc[base_allocation.index, 'pop_t0'] = gdf.loc[base_allocation.index, 'pop_t0'] + base_allocation
    return gdf


def ventiler_population_residentielle(jointure_gdf: gpd.GeoDataFrame, config: dict) -> gpd.GeoDataFrame:
    """
    Applique la formule de descente d'échelle dasymétrique pour les bâtiments résidentiels.
    Inclut la correction d'arrondi par la méthode du plus fort reste pour ne pas perdre d'agents.

    Parameters
    ----------
    jointure_gdf:
        Bâtiments déjà enrichis avec les variables du carreau Filosofi.
    config:
        Paramètres de scénario et d'initialisation.

    Returns
    -------
    geopandas.GeoDataFrame
        GeoDataFrame enrichi d'une colonne `pop_t0`.
    """
    logger.info("Début de la ventilation de la population résidentielle...")

    # 1. Extraction des variables
    r_rp = config['scenario']['residences']['r_rp']
    r_rs = config['scenario']['residences']['r_rs']
    tau_saison = config['scenario']['residences']['tau_saison']
    alpha_domicile = config['scenario']['residences']['alpha_domicile']
    fallback_sqm = config['filtering']['fallback_sqm_per_dwelling']

    gdf = jointure_gdf.copy()
    is_residentiel_brut = gdf['usage_1'].str.lower().str.contains('résidentiel|residentiel', na=False)
    is_residentiel = is_residentiel_brut.copy()
    excluded_culte_residential = pd.Series(False, index=gdf.index)
    if 'is_culte' in gdf.columns:
        culte_household_allowed = gdf.get('culte_household_allowed', True)
        is_residentiel = is_residentiel & (~gdf['is_culte'] | culte_household_allowed)
        excluded_culte_residential = is_residentiel_brut & ~is_residentiel
    gdf['pop_t0'] = 0

    # 2. Calcul des capacités
    gdf.loc[is_residentiel, 'capacite_logts'] = gdf[is_residentiel].apply(
        lambda row: calculer_capacite_residentielle(row, fallback_sqm), axis=1
    )

    gdf['somme_capacite_carreau'] = gdf.groupby('idcar_200m')['capacite_logts'].transform('sum')
    mask_valide = is_residentiel & (gdf['somme_capacite_carreau'] > 0)

    # 3. Formule mathématique corrigée
    # La population Filosofi représente les locaux (RP).
    # Les RS ajoutent un surplus potentiel de population selon la saison.
    # Formule : Pop_Bat = Pop_Carreau * (Cap_Bat / Cap_Totale) * [1 + (r_RS / r_RP) * tau_saison] * alpha_domicile

    ratio_spatial = gdf.loc[mask_valide, 'capacite_logts'] / gdf.loc[mask_valide, 'somme_capacite_carreau']
    modulateur_temporel = (1 + (r_rs / r_rp) * tau_saison) * alpha_domicile

    # Calcul de la population brute (en nombres flottants)
    pop_float = gdf.loc[mask_valide, 'ind'] * ratio_spatial * modulateur_temporel
    gdf.loc[mask_valide, 'pop_float'] = pop_float

    # 4. Traitement des arrondis (Méthode du plus fort reste)
    # On itère carreau par carreau pour répartir les restes décimaux
    for carreau_id, group in gdf[mask_valide].groupby('idcar_200m'):
        pop_theorique_carreau = group['pop_float'].sum()
        pop_cible_carreau = int(round(pop_theorique_carreau))

        # On donne la partie entière à chaque bâtiment
        parts_entieres = group['pop_float'].apply(np.floor).astype(int)

        # On calcule combien de personnes il manque à cause des arrondis
        personnes_manquantes = pop_cible_carreau - parts_entieres.sum()

        # On calcule les restes (ex: 0.8, 0.5, 0.2)
        restes = group['pop_float'] - parts_entieres

        # On trie les bâtiments par ceux qui ont le plus grand reste
        index_plus_forts_restes = restes.nlargest(personnes_manquantes).index

        # On ajoute 1 agent aux bâtiments avec les plus forts restes
        parts_entieres.loc[index_plus_forts_restes] += 1

        # On injecte le résultat final dans le DataFrame
        gdf.loc[group.index, 'pop_t0'] = parts_entieres

    # 5. Conservation de masse en cas d'exclusion culte sans bâti résidentiel alternatif local.
    # Certains carreaux peuvent n'avoir que du résidentiel classé culte non autorisé :
    # la population cible du carreau doit alors être redistribuée sur le reste du
    # parc résidentiel éligible pour ne pas créer de perte globale artificielle.
    missing_due_to_culte = 0
    if excluded_culte_residential.any():
        for _, group in gdf.groupby('idcar_200m'):
            if not excluded_culte_residential.loc[group.index].any():
                continue
            if mask_valide.loc[group.index].any():
                continue
            missing_due_to_culte += _target_population_for_carreau(group, modulateur_temporel)

    if missing_due_to_culte > 0:
        logger.warning(
            "Redistribution de %s agent(s) excludes du residentiel culte vers le parc residentiel eligible.",
            missing_due_to_culte,
        )
        gdf = _redistribute_missing_population(gdf, mask_valide, missing_due_to_culte)

    # Nettoyage de la colonne temporaire
    gdf = gdf.drop(columns=['pop_float', 'capacite_logts', 'somme_capacite_carreau'], errors='ignore')

    population_totale = gdf['pop_t0'].sum()
    logger.info(f"Ventilation terminée : {population_totale} agents placés.")

    return gdf
