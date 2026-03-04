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


def ventiler_population_residentielle(jointure_gdf: gpd.GeoDataFrame, config: dict) -> gpd.GeoDataFrame:
    """
    Applique la formule de descente d'échelle dasymétrique pour les bâtiments résidentiels.
    Inclut la correction d'arrondi par la méthode du plus fort reste pour ne pas perdre d'agents.
    """
    logger.info("Début de la ventilation de la population résidentielle...")

    # 1. Extraction des variables
    r_rp = config['scenario']['residences']['r_rp']
    r_rs = config['scenario']['residences']['r_rs']
    tau_saison = config['scenario']['residences']['tau_saison']
    alpha_domicile = config['scenario']['residences']['alpha_domicile']
    fallback_sqm = config['filtering']['fallback_sqm_per_dwelling']

    gdf = jointure_gdf.copy()
    is_residentiel = gdf['usage_1'].str.lower().str.contains('résidentiel|residentiel', na=False)
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

    # Nettoyage de la colonne temporaire
    gdf = gdf.drop(columns=['pop_float', 'capacite_logts', 'somme_capacite_carreau'])

    population_totale = gdf['pop_t0'].sum()
    logger.info(f"Ventilation terminée : {population_totale} agents placés.")

    return gdf