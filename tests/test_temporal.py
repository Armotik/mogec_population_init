import pytest
import geopandas as gpd
from shapely.geometry import Polygon
from src.core.agendas import generer_agendas_agents
from src.core.restaurants import integrer_restaurants_aux_batiments
from src.core.cultes import integrer_lieux_culte
from src.core.temporal import _resolve_role_profile, build_member_timelines, generer_matrice_horaire


def test_matrice_horaire_complete(config, bati_popule):
    # 1. Préparation de la donnée avec tous les attributs (Agendas, Restos, Cultes)
    config['data_paths']['input']['audit_restaurants'] = "data/01_raw/audit_restaurants_batz.csv"
    config['scenario']['day_of_week'] = "Dimanche"  # On force le dimanche pour tester l'église

    df = generer_agendas_agents(bati_popule, config)
    df = integrer_restaurants_aux_batiments(df, config)
    df = integrer_lieux_culte(df, config)

    # 2. Génération de la matrice 24h
    df_horaire = generer_matrice_horaire(df, config)

    # 3. Vérifications de base
    for h in range(24):
        assert f'pop_h{h}' in df_horaire.columns

    pop_totale_nuit = df_horaire['pop_h3'].sum()
    pop_totale_jour = df_horaire['pop_h15'].sum()

    print("\n" + "=" * 40)
    print(" VALIDATION DU CYCLE 24H (SCÉNARIO DIMANCHE)")
    print("=" * 40)
    print(f"Population Nuit (03h) : {pop_totale_nuit}")
    print(f"Population Jour (15h) : {pop_totale_jour}")

    # 4. Vérification des Lieux de Culte (Dimanche 10h)
    if 'is_culte' in df_horaire.columns and df_horaire['is_culte'].sum() > 0:
        batiments_cultes = df_horaire[df_horaire['is_culte'] == True]

        pop_culte_10h = batiments_cultes['pop_h10'].sum()
        pop_culte_03h = batiments_cultes['pop_h3'].sum()

        # On récupère le nombre de personnes qui "habitent" dans l'église (ex: Presbytère)
        pop_base_culte = batiments_cultes['pop_t0'].sum() if 'pop_t0' in batiments_cultes.columns else 0

        print(f"Agents à l'Église à 10h : {pop_culte_10h}")
        print(f"Agents à l'Église à 03h (Résidents permanents) : {pop_culte_03h}")

        assert pop_culte_10h > pop_base_culte, "L'église devrait attirer des fidèles le dimanche à 10h."
        # Le test vérifie maintenant que la nuit, la population redescend à son niveau de base (résidents)
        assert pop_culte_03h == pop_base_culte, f"La nuit, l'église ne devrait contenir que ses résidents ({pop_base_culte})."

    # 5. Vérification des Restaurants (Midi)
    if 'is_restaurant' in df_horaire.columns and df_horaire['is_restaurant'].sum() > 0:
        batiments_restos = df_horaire[df_horaire['is_restaurant'] == True]
        pop_restos_13h = batiments_restos['pop_h13'].sum()
        pop_restos_16h = batiments_restos['pop_h16'].sum()
        pop_restos_03h = batiments_restos['pop_h3'].sum()

        print(f"Agents aux Restaurants à 13h : {pop_restos_13h}")
        print(f"Agents aux Restaurants à 16h : {pop_restos_16h}")
        print(f"Agents aux Restaurants à 03h : {pop_restos_03h}")

        assert pop_restos_13h > pop_restos_16h, "Il devrait y avoir plus de monde au restaurant à 13h qu'à 16h."
        assert pop_restos_03h == batiments_restos['pop_t0'].sum(), "La nuit, un restaurant ne doit contenir que ses résidents éventuels."


def test_activites_exogenes_creent_un_pic_diurne(config):
    config['scenario']['day_of_week'] = "Jeudi"
    config['scenario']['temporal_context'] = {'weather_index': 1.0, 'alert_level': 0.0}
    config['non_residential_model']['activities']['enabled'] = True
    config['non_residential_model']['activities']['rules'] = [
        {
            'usage_any_of': ['Commercial et services'],
            'sqm_per_person': 20,
            'client_ratio': 1.0,
            'alpha_t0': 0.0,
            'hourly_profile': 'commerce_day',
        }
    ]
    config['non_residential_model']['activities']['profiles'] = {
        'commerce_day': {
            'hour_slots': [
                {'start': 11, 'end': 14, 'alpha': 0.5},
            ],
            'other_hours_alpha': 0.0,
        }
    }
    config['temporal_model']['modifiers']['activity_weather_sensitivity'] = 0.0
    config['temporal_model']['modifiers']['activity_alert_sensitivity'] = 0.0

    df = gpd.GeoDataFrame(
        {
            'building_id': ['B1'],
            'usage_1': ['Commercial et services'],
            'surface_sol': [100.0],
            'pop_t0': [0],
            'households': [[]],
        },
        geometry=[Polygon([(0, 0), (0, 10), (10, 10), (10, 0)])],
        crs='EPSG:2154',
    )

    resultat = generer_matrice_horaire(df, config)

    assert int(resultat['pop_h0'].sum()) == 0
    assert int(resultat['pop_h12'].sum()) > 0


def test_vacances_scolaires_n_annulent_pas_les_profils_actifs(config):
    config['scenario']['day_of_week'] = "Jeudi"
    config['scenario']['is_school_holiday'] = True

    profile_scolaire = _resolve_role_profile('scolaire', config)
    profile_actif_local = _resolve_role_profile('actif_local', config)
    profile_actif_navetteur = _resolve_role_profile('actif_navetteur', config)

    assert profile_scolaire.get('enabled') is False
    assert profile_actif_local.get('enabled') is True
    assert profile_actif_navetteur.get('enabled') is True


def test_scolaire_proche_peut_aller_a_pied():
    config = {
        'scenario': {
            'day_of_week': 'Jeudi',
            'is_school_holiday': False,
            'temporal_context': {},
        },
        'project': {'random_seed': 123},
        'temporal_model': {
            'calendars': {'weekend_days': ['Samedi', 'Dimanche']},
            'scenario_context': {'weather_index': 1.0, 'alert_level': 0.0, 'religious_day': False},
            'modifiers': {},
            'household_dynamics': {
                'enable_school_escort': True,
                'school_walk_max_distance_m': 500,
                'school_pickup_overlap_hours': 1,
            },
            'role_profiles': {
                'scolaire': {
                    'weekday': {
                        'enabled': True,
                        'departure': {'mean': 8.0, 'std': 0.0, 'min': 8, 'max': 8},
                        'return': {'mean': 16.0, 'std': 0.0, 'min': 16, 'max': 16},
                    }
                },
                'actif_local': {
                    'weekday': {
                        'enabled': True,
                        'departure': {'mean': 9.0, 'std': 0.0, 'min': 9, 'max': 9},
                        'return': {'mean': 18.0, 'std': 0.0, 'min': 18, 'max': 18},
                    }
                },
            },
        },
    }

    gdf = gpd.GeoDataFrame(
        {
            'building_id': ['HOME', 'SCHOOL', 'WORK'],
            'usage_1': ['Résidentiel', 'Enseignement', 'Commercial et services'],
            'households': [[{
                'household_id': 'HH1',
                'guardian_member_id': 'parent',
                'members': [
                    {'member_id': 'child', 'role': 'scolaire', 'destination_id': 'SCHOOL'},
                    {'member_id': 'parent', 'role': 'actif_local', 'destination_id': 'WORK'},
                ],
            }], [], []],
        },
        geometry=[
            Polygon([(0, 0), (0, 10), (10, 10), (10, 0)]),
            Polygon([(100, 0), (100, 10), (110, 10), (110, 0)]),
            Polygon([(1000, 0), (1000, 10), (1010, 10), (1010, 0)]),
        ],
        crs='EPSG:2154',
    )

    timelines = build_member_timelines(gdf, config)
    child = timelines.loc[timelines['member_id'] == 'child'].iloc[0]
    parent = timelines.loc[timelines['member_id'] == 'parent'].iloc[0]

    assert child['escort_mode'] == 'walk'
    assert child['school_access_status'] == 'walk'
    assert child['school_distance_m'] < 500
    assert parent['timeline_destinations'][8] == 'DOMICILE'
    assert parent['timeline_destinations'][9] == 'WORK'


def test_parent_peut_deposer_enfant_avant_travail():
    config = {
        'scenario': {
            'day_of_week': 'Jeudi',
            'is_school_holiday': False,
            'temporal_context': {},
        },
        'project': {'random_seed': 123},
        'temporal_model': {
            'calendars': {'weekend_days': ['Samedi', 'Dimanche']},
            'scenario_context': {'weather_index': 1.0, 'alert_level': 0.0, 'religious_day': False},
            'modifiers': {},
            'household_dynamics': {
                'enable_school_escort': True,
                'school_walk_max_distance_m': 500,
                'school_pickup_overlap_hours': 1,
            },
            'role_profiles': {
                'scolaire': {
                    'weekday': {
                        'enabled': True,
                        'departure': {'mean': 8.0, 'std': 0.0, 'min': 8, 'max': 8},
                        'return': {'mean': 17.0, 'std': 0.0, 'min': 17, 'max': 17},
                    }
                },
                'actif_local': {
                    'weekday': {
                        'enabled': True,
                        'departure': {'mean': 8.0, 'std': 0.0, 'min': 8, 'max': 8},
                        'return': {'mean': 18.0, 'std': 0.0, 'min': 18, 'max': 18},
                    }
                },
            },
        },
    }

    gdf = gpd.GeoDataFrame(
        {
            'building_id': ['HOME', 'SCHOOL', 'WORK'],
            'usage_1': ['Résidentiel', 'Enseignement', 'Commercial et services'],
            'households': [[{
                'household_id': 'HH1',
                'guardian_member_id': 'parent',
                'members': [
                    {'member_id': 'child', 'role': 'scolaire', 'destination_id': 'SCHOOL'},
                    {'member_id': 'parent', 'role': 'actif_local', 'destination_id': 'WORK'},
                ],
            }], [], []],
        },
        geometry=[
            Polygon([(0, 0), (0, 10), (10, 10), (10, 0)]),
            Polygon([(1200, 0), (1200, 10), (1210, 10), (1210, 0)]),
            Polygon([(2000, 0), (2000, 10), (2010, 10), (2010, 0)]),
        ],
        crs='EPSG:2154',
    )

    timelines = build_member_timelines(gdf, config)
    child = timelines.loc[timelines['member_id'] == 'child'].iloc[0]
    parent = timelines.loc[timelines['member_id'] == 'parent'].iloc[0]

    assert child['escort_mode'] == 'escort'
    assert child['school_access_status'] == 'escort'
    assert child['escort_guardian_id'] == 'parent'
    assert child['school_distance_m'] > 500
    assert parent['timeline_destinations'][8] == 'SCHOOL'
    assert parent['timeline_destinations'][9] == 'WORK'
    assert 17 in parent['escort_stop_hours']


def test_scolaire_peut_revenir_a_domicile_le_midi():
    config = {
        'scenario': {
            'day_of_week': 'Jeudi',
            'is_school_holiday': False,
            'temporal_context': {},
        },
        'project': {'random_seed': 123},
        'temporal_model': {
            'calendars': {'weekend_days': ['Samedi', 'Dimanche']},
            'scenario_context': {'weather_index': 1.0, 'alert_level': 0.0, 'religious_day': False},
            'modifiers': {},
            'household_dynamics': {
                'enable_school_escort': False,
                'school_walk_max_distance_m': 500,
                'school_pickup_overlap_hours': 1,
            },
            'role_profiles': {
                'scolaire': {
                    'weekday': {
                        'enabled': True,
                        'departure': {'mean': 8.0, 'std': 0.0, 'min': 8, 'max': 8},
                        'return': {'mean': 16.0, 'std': 0.0, 'min': 16, 'max': 16},
                        'lunch': {
                            'hours': [12, 13],
                            'at_home_probability_by_hour': {12: 1.0, 13: 0.0},
                        },
                    }
                },
            },
        },
    }

    gdf = gpd.GeoDataFrame(
        {
            'building_id': ['HOME', 'SCHOOL'],
            'usage_1': ['Résidentiel', 'Enseignement'],
            'households': [[{
                'household_id': 'HH1',
                'guardian_member_id': None,
                'members': [
                    {'member_id': 'child', 'role': 'scolaire', 'destination_id': 'SCHOOL'},
                ],
            }], []],
        },
        geometry=[
            Polygon([(0, 0), (0, 10), (10, 10), (10, 0)]),
            Polygon([(100, 0), (100, 10), (110, 10), (110, 0)]),
        ],
        crs='EPSG:2154',
    )

    timelines = build_member_timelines(gdf, config)
    child = timelines.loc[timelines['member_id'] == 'child'].iloc[0]

    assert child['timeline_destinations'][9] == 'SCHOOL'
    assert child['timeline_destinations'][12] == 'DOMICILE'
    assert child['timeline_destinations'][13] == 'SCHOOL'


def test_scolaire_respecte_un_profil_horaire_de_presence():
    config = {
        'scenario': {
            'day_of_week': 'Jeudi',
            'is_school_holiday': False,
            'temporal_context': {},
        },
        'project': {'random_seed': 123},
        'temporal_model': {
            'calendars': {'weekend_days': ['Samedi', 'Dimanche']},
            'scenario_context': {'weather_index': 1.0, 'alert_level': 0.0, 'religious_day': False},
            'modifiers': {},
            'household_dynamics': {
                'enable_school_escort': False,
                'school_walk_max_distance_m': 500,
                'school_pickup_overlap_hours': 1,
            },
            'role_profiles': {
                'scolaire': {
                    'weekday': {
                        'enabled': True,
                        'departure': {'mean': 8.0, 'std': 0.0, 'min': 8, 'max': 8},
                        'return': {'mean': 16.0, 'std': 0.0, 'min': 16, 'max': 16},
                        'attendance_probability_by_hour': {
                            8: 0.0,
                            9: 1.0,
                            10: 1.0,
                            11: 1.0,
                            12: 0.0,
                            13: 0.0,
                            14: 1.0,
                            15: 1.0,
                            16: 0.0,
                        },
                    }
                },
            },
        },
    }

    gdf = gpd.GeoDataFrame(
        {
            'building_id': ['HOME', 'SCHOOL'],
            'usage_1': ['Résidentiel', 'Enseignement'],
            'households': [[{
                'household_id': 'HH1',
                'guardian_member_id': None,
                'members': [
                    {'member_id': 'child', 'role': 'scolaire', 'destination_id': 'SCHOOL'},
                ],
            }], []],
        },
        geometry=[
            Polygon([(0, 0), (0, 10), (10, 10), (10, 0)]),
            Polygon([(100, 0), (100, 10), (110, 10), (110, 0)]),
        ],
        crs='EPSG:2154',
    )

    timelines = build_member_timelines(gdf, config)
    child = timelines.loc[timelines['member_id'] == 'child'].iloc[0]

    assert child['timeline_destinations'][8] == 'DOMICILE'
    assert child['timeline_destinations'][9] == 'SCHOOL'
    assert child['timeline_destinations'][12] == 'DOMICILE'
    assert child['timeline_destinations'][14] == 'SCHOOL'
    assert child['timeline_destinations'][16] == 'DOMICILE'
