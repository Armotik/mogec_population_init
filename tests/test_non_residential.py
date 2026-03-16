from pathlib import Path

import geopandas as gpd
import pandas as pd
from shapely.geometry import Polygon

from src.core.non_residential import ajouter_zones_plage_exogenes, integrer_population_non_residentielle
from src.core.temporal import generer_matrice_horaire


def _base_config():
    return {
        'scenario': {
            'day_of_week': 'Jeudi',
            'is_school_holiday': False,
            'temporal_context': {},
            'tourisme': {'tau_meteo': 0.5},
        },
        'temporal_model': {
            'calendars': {'weekend_days': ['Samedi', 'Dimanche']},
            'scenario_context': {'weather_index': 1.0, 'alert_level': 0.0, 'religious_day': False},
            'modifiers': {},
            'household_dynamics': {'enable_school_escort': False},
            'role_profiles': {'senior': {'weekday': {}}},
        },
        'project': {'building_id': {'prefix': 'TEST'}},
        'non_residential_model': {
            'accommodation': {
                'enabled': False,
                'capacity_table': '',
                'join_key': 'building_id',
                'capacity_column': 'capacity_lits',
                'tau_occupation': 0.5,
                'alpha_tourist_t0': 0.8,
                'evidence': {'formula': 'ok', 'source_name': 'ok', 'confidence': 'ok'},
            },
            'activities': {
                'enabled': False,
                'rules': [],
                'evidence': {'formula': 'ok', 'source_name': 'ok', 'confidence': 'ok'},
            },
            'beaches': {
                'enabled': False,
                'zones_path': '',
                'zones_layer': '',
                'zone_id_column': 'zone_id',
                'sqm_per_person': 5.0,
                'hour_slots': [{'start': 12, 'end': 16, 'alpha': 1.0}],
                'other_hours_alpha': 0.1,
                'evidence': {'formula': 'ok', 'source_name': 'ok', 'confidence': 'ok'},
            },
        },
    }


def test_integrer_population_non_residentielle(tmp_path):
    config = _base_config()
    capacity_csv = tmp_path / "beds.csv"
    pd.DataFrame([{'building_id': 'TEST_B1', 'capacity_lits': 40}]).to_csv(capacity_csv, index=False)

    config['non_residential_model']['accommodation']['enabled'] = True
    config['non_residential_model']['accommodation']['capacity_table'] = str(capacity_csv)
    config['non_residential_model']['activities']['enabled'] = True
    config['non_residential_model']['activities']['rules'] = [
        {'usage_any_of': ['Commercial et services'], 'sqm_per_person': 20, 'client_ratio': 1.0, 'alpha_t0': 0.5}
    ]

    gdf = gpd.GeoDataFrame(
        {
            'building_id': ['TEST_B1', 'TEST_B2'],
            'usage_1': ['Indifférencié', 'Commercial et services'],
            'surface_sol': [100.0, 200.0],
            'pop_t0': [0, 0],
        },
        geometry=[
            Polygon([(0, 0), (0, 10), (10, 10), (10, 0)]),
            Polygon([(20, 0), (20, 10), (30, 10), (30, 0)]),
        ],
        crs='EPSG:2154'
    )

    resultat = integrer_population_non_residentielle(gdf, config)

    assert int(resultat.loc[resultat['building_id'] == 'TEST_B1', 'pop_nonres_accommodation'].iloc[0]) == 16
    assert int(resultat.loc[resultat['building_id'] == 'TEST_B2', 'pop_nonres_activity'].iloc[0]) == 10


def test_prevenir_double_comptage_hebergement_residentiel(tmp_path):
    config = _base_config()
    capacity_csv = tmp_path / "beds_overlap.csv"
    pd.DataFrame(
        [
            {
                'building_id': 'TEST_B1',
                'capacity_lits': 20,
                'source_types': 'locative',
                'offer_names': 'Maison test',
            },
            {
                'building_id': 'TEST_B2',
                'capacity_lits': 12,
                'source_types': 'hotel',
                'offer_names': 'Hotel test',
            },
        ]
    ).to_csv(capacity_csv, index=False)

    config['non_residential_model']['accommodation']['enabled'] = True
    config['non_residential_model']['accommodation']['capacity_table'] = str(capacity_csv)
    config['non_residential_model']['accommodation']['tau_occupation'] = 1.0
    config['non_residential_model']['accommodation']['alpha_tourist_t0'] = 1.0
    config['non_residential_model']['accommodation']['double_count_prevention'] = {
        'enabled': True,
        'residential_usage_any_of': ['Résidentiel'],
        'exclude_source_types_on_residential': ['locative'],
        'warn_source_types_on_residential': ['residence'],
    }

    gdf = gpd.GeoDataFrame(
        {
            'building_id': ['TEST_B1', 'TEST_B2'],
            'usage_1': ['Résidentiel', 'Commercial et services'],
            'surface_sol': [100.0, 150.0],
            'pop_t0': [4, 0],
        },
        geometry=[
            Polygon([(0, 0), (0, 10), (10, 10), (10, 0)]),
            Polygon([(20, 0), (20, 10), (30, 10), (30, 0)]),
        ],
        crs='EPSG:2154'
    )

    resultat = integrer_population_non_residentielle(gdf, config)

    locatif = resultat[resultat['building_id'] == 'TEST_B1'].iloc[0]
    hotel = resultat[resultat['building_id'] == 'TEST_B2'].iloc[0]

    assert int(locatif['pop_nonres_accommodation']) == 0
    assert int(locatif['accommodation_capacity_raw']) == 20
    assert int(locatif['accommodation_capacity_retained']) == 0
    assert locatif['accommodation_overlap_risk'] == 'high'
    assert locatif['accommodation_overlap_action'] == 'excluded_residential_overlap'

    assert int(hotel['pop_nonres_accommodation']) == 12
    assert int(hotel['accommodation_capacity_retained']) == 12
    assert hotel['accommodation_overlap_risk'] == 'low'


def test_ajouter_zones_plage_exogenes_et_matrice(tmp_path):
    config = _base_config()
    beach_geojson = tmp_path / "beaches.geojson"
    config['non_residential_model']['beaches']['enabled'] = True
    config['non_residential_model']['beaches']['zones_path'] = str(beach_geojson)

    beach = gpd.GeoDataFrame(
        {'zone_id': ['A']},
        geometry=[Polygon([(0, 0), (0, 50), (50, 50), (50, 0)])],
        crs='EPSG:2154'
    )
    beach.to_file(beach_geojson, driver='GeoJSON')

    base = gpd.GeoDataFrame(
        {
            'building_id': ['TEST_B1'],
            'building_id_source': ['test'],
            'usage_1': ['Résidentiel'],
            'nature': ['Indifférenciée'],
            'hauteur': [5.0],
            'surface_sol': [100.0],
            'pop_t0': [0],
            'dest_id': [None],
            'prob_senior': [0.0],
            'prob_enfant': [0.0],
            'prob_pauvrete': [0.0],
            'n_scolaire': [0],
            'n_senior': [0],
            'n_actif_local': [0],
            'n_actif_navetteur': [0],
            'n_households': [0],
            'is_restaurant': [False],
            'nom_resto': ["None"],
            'horaires_osm': ["None"],
            'horaires_source': ["none"],
            'restaurant_service_slots': [""],
            'is_culte': [False],
            'nom_culte': ["None"],
            'households': [[]],
            'liste_roles': [[]],
        },
        geometry=[Polygon([(100, 0), (100, 10), (110, 10), (110, 0)])],
        crs='EPSG:2154'
    )

    with_beach = ajouter_zones_plage_exogenes(base, config)
    resultat = generer_matrice_horaire(with_beach, config)

    beach_row = resultat[resultat['exogenous_zone_type'] == 'plage'].iloc[0]
    assert int(beach_row['pop_h12']) == 250
    assert int(beach_row['pop_h0']) == 25
