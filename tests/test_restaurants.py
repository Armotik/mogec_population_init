import pytest
from pathlib import Path
from src.core.restaurants import integrer_restaurants_aux_batiments


def test_integration_restaurants(config, bati_popule):
    """
    Vérifie que la fonction d'intégration des restaurants modifie
    correctement le GeoDataFrame des bâtiments.
    """
    # Ajout temporaire du chemin au config pour le test
    # (Assure-toi que ce fichier existe bien suite à ton audit)
    config['data_paths']['input']['audit_restaurants'] = "data/01_raw/audit_restaurants_batz.csv"

    assert Path(config['data_paths']['input']['audit_restaurants']).exists(), \
        "Le fichier d'audit OSM doit exister pour lancer ce test."

    # Appel de la fonction
    df_resultat = integrer_restaurants_aux_batiments(bati_popule, config)

    # Vérifications structurelles
    assert 'is_restaurant' in df_resultat.columns
    assert 'nom_resto' in df_resultat.columns
    assert 'horaires_osm' in df_resultat.columns

    # Vérifications logiques
    nombre_restaurants = df_resultat['is_restaurant'].sum()

    print(f"\n[Validation Restaurants]")
    print(f"Nombre de bâtiments classés comme restaurants : {nombre_restaurants}")

    # On sait qu'il y a 13 points dans ton fichier brut.
    # Avec la tolérance de 20m, on devrait en retrouver la majorité.
    assert nombre_restaurants > 0, "Aucun restaurant n'a été lié aux bâtiments."
    assert nombre_restaurants <= 15, "Trop de restaurants ont été liés (erreur de tolérance probable)."

    # Vérification d'un attribut textuel
    restos_noms = df_resultat[df_resultat['is_restaurant']]['nom_resto'].tolist()
    assert any(nom != "None" for nom in restos_noms), "Les noms des restaurants n'ont pas été transférés."