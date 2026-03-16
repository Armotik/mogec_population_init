import pytest
import pandas as pd
from pathlib import Path
from src.core.restaurants import integrer_restaurants_aux_batiments, restaurants_ouverts_a_l_heure
import geopandas as gpd


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
    assert 'horaires_source' in df_resultat.columns
    assert 'restaurant_service_slots' in df_resultat.columns

    # Vérifications logiques
    nombre_restaurants = df_resultat['is_restaurant'].sum()

    print(f"\n[Validation Restaurants]")
    print(f"Nombre de bâtiments classés comme restaurants : {nombre_restaurants}")

    # On sait qu'il y a 13 points dans ton fichier brut.
    # Avec la tolérance de 20m, on devrait en retrouver la majorité.
    assert nombre_restaurants >= 2, "Le matching devrait maintenant retrouver les deux restaurants du fichier d'audit."
    assert nombre_restaurants <= 15, "Trop de restaurants ont été liés (erreur de tolérance probable)."

    # Vérification d'un attribut textuel
    restos_noms = df_resultat[df_resultat['is_restaurant']]['nom_resto'].tolist()
    assert any(nom != "None" for nom in restos_noms), "Les noms des restaurants n'ont pas été transférés."


def test_imputation_horaires_restaurants(tmp_path, config, bati_nettoye):
    """
    Vérifie que les horaires manquants sont imputés de façon stable.
    """
    csv_path = tmp_path / "restaurants_missing_hours.csv"
    centroid_wgs84 = gpd.GeoSeries([bati_nettoye.geometry.centroid.iloc[0]], crs=bati_nettoye.crs).to_crs(4326).iloc[0]
    pd.DataFrame(
        [
            {
                'osm_id': 'node/1',
                'nom': 'Resto Test',
                'lat': centroid_wgs84.y,
                'lon': centroid_wgs84.x,
                'opening_hours_brut': None,
                'horaire_ouverture': None,
                'horaire_fermeture': None,
            }
        ]
    ).to_csv(csv_path, sep=';', index=False)

    config['data_paths']['input']['audit_restaurants'] = str(csv_path)
    resultat_a = integrer_restaurants_aux_batiments(bati_nettoye, config)
    resultat_b = integrer_restaurants_aux_batiments(bati_nettoye, config)

    resto_a = resultat_a[resultat_a['is_restaurant'] == True]
    resto_b = resultat_b[resultat_b['is_restaurant'] == True]

    assert not resto_a.empty
    assert resto_a['horaires_source'].iloc[0].startswith("imputed:")
    assert resto_a['restaurant_service_slots'].iloc[0] == resto_b['restaurant_service_slots'].iloc[0]


def test_restaurants_ouverts_a_l_heure(config, bati_popule):
    """
    Vérifie que la sélection horaire exclut les restaurants fermés.
    """
    config['data_paths']['input']['audit_restaurants'] = "data/01_raw/audit_restaurants_batz.csv"
    df_resultat = integrer_restaurants_aux_batiments(bati_popule, config)

    ouverts_13h = restaurants_ouverts_a_l_heure(df_resultat, 13)
    ouverts_3h = restaurants_ouverts_a_l_heure(df_resultat, 3)

    assert len(ouverts_13h) >= 1
    assert len(ouverts_3h) == 0
