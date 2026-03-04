import pytest
import geopandas as gpd
import pandas as pd
from pathlib import Path


def test_validation_scientifique_export(config):
    """
    Analyse le fichier final pour valider la cohérence
    scientifique et spatiale des données exportées.
    """
    path_export = Path(config['data_paths']['output']['final_export'])

    assert path_export.exists(), "Le fichier exporté est introuvable."

    # 1. Chargement du résultat final
    gdf = gpd.read_file(path_export)

    # --- A. VALIDATION DES VOLUMES (Validité externe) ---
    pop_totale = gdf['pop_t0'].sum()
    batiments_occupes = len(gdf[gdf['pop_t0'] > 0])

    # Rappel des chiffres de référence (Recensement permanent)
    ref_insee_permanent = 2799

    print(f"\n" + "=" * 50)
    print(f"   BILAN DE VALIDATION SCIENTIFIQUE : BATZ-SUR-MER")
    print(f"=" * 50)
    print(f"Population totale générée : {pop_totale:.0f} agents")
    print(f"Nombre de bâtiments habités : {batiments_occupes}")

    # Calcul de l'écart par rapport au permanent (population saisonnière estimée)
    surplus_saisonnier = pop_totale - ref_insee_permanent
    print(f"Estimation population flottante (RS) : {surplus_saisonnier:.0f} agents")

    # --- B. VALIDATION DE LA CENTRALITÉ (Analyse de densité) ---
    # On calcule la densité d'occupation (agents par m2 de sol)
    gdf['densite_relative'] = gdf['pop_t0'] / gdf.geometry.area

    # On isole le top 10% des bâtiments les plus denses (le "Cœur de ville")
    seuil_densite = gdf['densite_relative'].quantile(0.90)
    top_10_denses = gdf[gdf['densite_relative'] >= seuil_densite]

    densite_moyenne_globale = gdf[gdf['pop_t0'] > 0]['densite_relative'].mean()
    densite_moyenne_centre = top_10_denses['densite_relative'].mean()

    ratio_centralite = densite_moyenne_centre / densite_moyenne_globale

    print(f"\n--- ANALYSE DE LA STRUCTURE URBAINE ---")
    print(f"Densité moyenne d'occupation : {densite_moyenne_globale:.6f} agents/m²")
    print(f"Densité dans les zones denses : {densite_moyenne_centre:.6f} agents/m²")
    print(f"Indice de centralité : {ratio_centralite:.2f}x")

    # --- C. VALIDATION DU PROFILAGE ---
    moyenne_senior = gdf[gdf['pop_t0'] > 0]['prob_senior'].mean()
    print(f"\n--- ANALYSE SOCIODÉMOGRAPHIQUE ---")
    print(f"Part moyenne de seniors (65+) : {moyenne_senior:.2%}")

    # --- D. ASSERTIONS SCIENTIFIQUES ---
    # 1. La population doit être supérieure au recensement permanent (car occupation RS > 0)
    assert pop_totale > ref_insee_permanent, "Erreur : La population ne peut pas être inférieure au recensement permanent."

    # 2. L'indice de centralité doit montrer une différenciation (typiquement > 1.5)
    assert ratio_centralite > 1.5, "Alerte : Le modèle ne semble pas différencier assez les centres des périphéries."

    # 3. La population ne doit pas dépasser la capacité de charge maximale (ex: 9000)
    assert pop_totale < 9000, "Erreur : Population physiquement impossible pour la commune."

    print(f"\n[RÉSULTAT] : VALIDATION SCIENTIFIQUE RÉUSSIE")
    print(f"=" * 50)