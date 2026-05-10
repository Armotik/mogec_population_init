import pytest
from pathlib import Path

from src.io.config_validation import validate_config_for_evidence
from src.pipeline import load_config


def test_validate_config_for_evidence_rejects_enabled_section_without_proof():
    config = {
        'non_residential_model': {
            'accommodation': {
                'enabled': True,
                'evidence': {
                    'formula': '',
                    'source_name': '',
                    'source_url': '',
                    'extraction_date': '',
                    'confidence': '',
                }
            },
            'activities': {'enabled': False, 'evidence': {}},
            'beaches': {'enabled': False, 'evidence': {}},
        }
    }

    with pytest.raises(ValueError):
        validate_config_for_evidence(config)


def test_validate_config_for_evidence_accepts_traceable_proof():
    config = {
        'non_residential_model': {
            'accommodation': {
                'enabled': True,
                'evidence': {
                    'formula': 'Pop = capacite * tau * alpha',
                    'source_name': 'Base regionale tourisme',
                    'source_url': 'https://example.org/source',
                    'source_file': '',
                    'extraction_date': '2026-03-10',
                    'confidence': 'medium',
                }
            },
            'activities': {'enabled': False, 'evidence': {}},
            'beaches': {'enabled': False, 'evidence': {}},
        }
    }

    validate_config_for_evidence(config)


def test_validate_config_for_evidence_rejects_invalid_temporal_proxy():
    config = {
        'non_residential_model': {
            'accommodation': {'enabled': False, 'evidence': {}},
            'activities': {'enabled': False, 'evidence': {}},
            'beaches': {'enabled': False, 'evidence': {}},
        },
        'proxy_validation': {
            'temporal_proxies': [
                {
                    'proxy_id': 'proxy_scolaire',
                    'metric': 'role_state_share',
                    'role': 'scolaire',
                    'state': 'interne',
                    'comparison_normalization': 'max',
                    'reference_curve': [0.0] * 12,
                    'thresholds': {
                        'correlation_pass_min': 0.8,
                        'correlation_warn_min': 0.6,
                        'rmse_pass_max': 0.1,
                        'rmse_warn_max': 0.2,
                        'peak_gap_pass_max_hours': 1,
                        'peak_gap_warn_max_hours': 2,
                    },
                    'evidence': {
                        'formula': 'part_scolaire_interne(t)',
                        'source_name': 'Source de test',
                        'source_url': 'https://example.org/source',
                        'source_file': '',
                        'extraction_date': '2026-03-24',
                        'confidence': 'medium',
                    },
                }
            ]
        },
    }

    with pytest.raises(ValueError):
        validate_config_for_evidence(config)


def test_validate_config_for_evidence_accepts_dict_reference_curve():
    config = {
        'non_residential_model': {
            'accommodation': {'enabled': False, 'evidence': {}},
            'activities': {'enabled': False, 'evidence': {}},
            'beaches': {'enabled': False, 'evidence': {}},
        },
        'proxy_validation': {
            'temporal_proxies': [
                {
                    'proxy_id': 'proxy_dict_curve',
                    'metric': 'role_internal_assigned_state_share',
                    'role': 'scolaire',
                    'state': 'interne',
                    'comparison_normalization': 'max',
                    'reference_curve': {hour: float(hour) for hour in range(24)},
                    'thresholds': {
                        'correlation_pass_min': 0.8,
                        'correlation_warn_min': 0.6,
                        'rmse_pass_max': 0.1,
                        'rmse_warn_max': 0.2,
                        'peak_gap_pass_max_hours': 1,
                        'peak_gap_warn_max_hours': 2,
                    },
                    'evidence': {
                        'formula': 'part_scolaire_interne(t)',
                        'source_name': 'Source de test',
                        'source_url': 'https://example.org/source',
                        'source_file': '',
                        'extraction_date': '2026-03-24',
                        'confidence': 'medium',
                    },
                }
            ]
        },
    }

    validate_config_for_evidence(config)


def test_validate_config_for_evidence_rejects_internal_role_proxy_without_state():
    config = {
        'non_residential_model': {
            'accommodation': {'enabled': False, 'evidence': {}},
            'activities': {'enabled': False, 'evidence': {}},
            'beaches': {'enabled': False, 'evidence': {}},
        },
        'proxy_validation': {
            'temporal_proxies': [
                {
                    'proxy_id': 'proxy_internal_role_missing_state',
                    'metric': 'role_internal_assigned_state_share',
                    'role': 'scolaire',
                    'comparison_normalization': 'max',
                    'reference_curve': [0.0] * 24,
                    'thresholds': {
                        'correlation_pass_min': 0.8,
                        'correlation_warn_min': 0.6,
                        'rmse_pass_max': 0.1,
                        'rmse_warn_max': 0.2,
                        'peak_gap_pass_max_hours': 1,
                        'peak_gap_warn_max_hours': 2,
                    },
                    'evidence': {
                        'formula': 'part_scolaire_interne(t)',
                        'source_name': 'Source de test',
                        'source_url': 'https://example.org/source',
                        'source_file': '',
                        'extraction_date': '2026-03-24',
                        'confidence': 'medium',
                    },
                }
            ]
        },
    }

    with pytest.raises(ValueError):
        validate_config_for_evidence(config)


def test_validate_config_for_evidence_rejects_invalid_school_hour_probability():
    config = {
        'non_residential_model': {
            'accommodation': {'enabled': False, 'evidence': {}},
            'activities': {'enabled': False, 'evidence': {}},
            'beaches': {'enabled': False, 'evidence': {}},
        },
        'temporal_model': {
            'calendars': {'weekend_days': ['Samedi', 'Dimanche']},
            'scenario_context': {
                'season': 'winter',
                'weather_index': 0.2,
                'alert_level': 0.8,
                'religious_day': False,
            },
            'modifiers': {
                'leisure_weather_sensitivity': 0.5,
                'leisure_alert_sensitivity': 0.8,
                'restaurant_weather_sensitivity': 0.35,
                'restaurant_alert_sensitivity': 0.7,
                'activity_weather_sensitivity': 0.6,
                'activity_alert_sensitivity': 0.7,
            },
            'household_dynamics': {
                'enable_school_escort': True,
                'school_walk_max_distance_m': 1200,
                'school_pickup_overlap_hours': 1,
            },
            'role_profiles': {
                'scolaire': {
                    'weekday': {
                        'attendance_probability_by_hour': {
                            8: 1.2,
                        }
                    },
                    'holiday': {'enabled': False},
                    'weekend': {'enabled': False},
                },
                'actif_local': {},
                'actif_navetteur': {},
                'senior': {},
            }
        },
    }

    with pytest.raises(ValueError):
        validate_config_for_evidence(config)


def test_validate_config_for_evidence_rejects_unknown_top_level_section_in_complete_mode():
    config = {
        'project': {'name': 'test', 'crs_epsg': 2154, 'random_seed': 1, 'building_id': {'prefix': 'X', 'source_priority': ['a']}},
        'study_area': {
            'commune_name': 'Test',
            'commune_insee': '00000',
            'boundary_path': '/tmp/boundary.gpkg',
            'boundary_layer': 'commune',
            'boundary_name_field': 'name',
            'boundary_name_value': 'Test',
            'department_code': '00',
            'buffer_m': 0,
        },
        'data_paths': {
            'input': {
                'bd_topo': '/tmp/a',
                'bd_topo_layer': 'batiment',
                'bdnb': '/tmp/b',
                'filosofi': '/tmp/c',
                'schools_csv': '/tmp/d',
                'tourism_restaurants': '/tmp/e',
                'tourism_hotels': '/tmp/f',
                'tourism_campings': '/tmp/g',
                'tourism_residences': '/tmp/h',
                'tourism_collective': '/tmp/i',
                'tourism_locative': '/tmp/j',
                'beaches_raw': '/tmp/k',
                'tourism_capacity_insee': '/tmp/l',
                'audit_restaurants': '/tmp/m',
            },
            'output': {'interim_dir': '/tmp/out', 'final_export': '/tmp/out/result.gpkg'},
        },
        'external_preparation': {},
        'visualization': {},
        'filtering': {'min_building_area_m2': 9, 'fallback_sqm_per_dwelling': 80},
        'demographics': {
            'age_pyramid': {'under_15': 0.1, 'from_15_to_64': 0.5, 'over_65': 0.4},
            'employment': {'total_emplois_lieu_travail': 10, 'travail_local_pct': 0.4, 'navetteurs_ext_pct': 0.6},
            'households': {
                'enforce_exact_role_targets': True,
                'size_distribution': {'1': 0.5, '2': 0.5},
                'family_household_pct': 0.3,
                'child_household_adult_min': 1,
                'two_adults_if_children_pct': 0.6,
                'single_senior_pct': 0.4,
                'family_guardian': {'actif_local_pct': 0.4, 'actif_navetteur_pct': 0.5, 'senior_pct': 0.1},
            },
        },
        'destination_model': {
            'fallback_destination': 'EXTERIEUR',
            'default_max_distance_m': 1000,
            'min_distance_m': 20,
            'distance_decay': 1.0,
            'role_pools': {
                'scolaire': {'usage_any_of': ['Enseignement'], 'max_distance_m': 100, 'distance_decay': 1.0},
                'actif_local': {'usage_any_of': ['Commercial et services'], 'max_distance_m': 100, 'distance_decay': 1.0},
            },
        },
        'temporal_model': {
            'calendars': {'weekend_days': ['Samedi', 'Dimanche']},
            'scenario_context': {'season': 'winter', 'weather_index': 0.2, 'alert_level': 0.1, 'religious_day': False},
            'modifiers': {
                'leisure_weather_sensitivity': 0.5,
                'leisure_alert_sensitivity': 0.5,
                'restaurant_weather_sensitivity': 0.5,
                'restaurant_alert_sensitivity': 0.5,
                'activity_weather_sensitivity': 0.5,
                'activity_alert_sensitivity': 0.5,
            },
            'household_dynamics': {'enable_school_escort': True, 'school_walk_max_distance_m': 10, 'school_pickup_overlap_hours': 1},
            'role_profiles': {'scolaire': {}, 'actif_local': {}, 'actif_navetteur': {}, 'senior': {}},
        },
        'poi_matching': {
            'restaurants': {
                'max_distance_m': 10,
                'preferred_usage_any_of': ['Commercial et services'],
                'allow_fallback_any_usage': True,
                'concat_multiple_names': True,
                'evidence': {},
            }
        },
        'non_residential_model': {
            'accommodation': {'enabled': False, 'evidence': {}},
            'activities': {'enabled': False, 'evidence': {}},
            'beaches': {'enabled': False, 'evidence': {}},
        },
        'infrastructures': {
            'schools': {'a': {'capacity': 1, 'name': 'A', 'latitude': 1.0, 'longitude': 1.0}},
            'school_matching': {'match_max_distance_m': 1, 'min_building_area_m2': 1, 'preferred_usage_any_of': ['Enseignement']},
            'schedules': {'school_start': '08:30', 'school_end': '16:30', 'work_start': '08:30', 'work_end': '18:00'},
        },
        'scenario': {
            'name': 'test',
            'day_of_week': 'Jeudi',
            'is_school_holiday': False,
            'reference_hour': 10,
            'residences': {'r_rp': 0.35, 'r_rs': 0.61, 'tau_saison': 0.1, 'alpha_domicile': 0.7},
            'commerce': {'sqm_per_employee': 30, 'client_employee_ratio': 4, 'alpha_commerce': 0.0},
            'tourisme': {'tau_meteo': 0.1, 'alpha_plage': 0.0, 'tau_occupation_lits': 0.1},
            'temporal_context': {'season': 'winter', 'weather_index': 0.1, 'alert_level': 0.0, 'religious_day': False},
        },
        'proxy_validation': {
            'scenario_sets': {'default': [{'config_path': '/tmp/test.yaml'}]},
            'temporal_proxies': [{
                'proxy_id': 'p',
                'metric': 'role_state_share',
                'role': 'scolaire',
                'state': 'interne',
                'comparison_normalization': 'none',
                'reference_curve': [0.0] * 24,
                'thresholds': {
                    'correlation_pass_min': 0.8,
                    'correlation_warn_min': 0.6,
                    'rmse_pass_max': 0.1,
                    'rmse_warn_max': 0.2,
                    'peak_gap_pass_max_hours': 1,
                    'peak_gap_warn_max_hours': 2,
                },
                'evidence': {
                    'formula': 'x',
                    'source_name': 'y',
                    'source_url': 'https://example.org',
                    'source_file': '',
                    'extraction_date': '2026-03-24',
                    'confidence': 'medium',
                },
            }],
        },
        'unexpected': {},
    }

    with pytest.raises(ValueError):
        validate_config_for_evidence(config, require_complete=True)


def test_load_config_supports_extends():
    config = load_config(Path("config_summer_day.yaml"))

    assert config['scenario']['name'] == "summer_weekday_day"
    assert config['scenario']['temporal_context']['season'] == "summer"
    assert Path(config['data_paths']['output']['final_export']).name == "population_batz_t0.gpkg"


def test_load_config_resolves_relative_paths_from_yaml_directory(tmp_path, monkeypatch):
    config_dir = tmp_path / "configs"
    data_dir = tmp_path / "data"
    output_dir = tmp_path / "out"
    other_cwd = tmp_path / "elsewhere"
    config_dir.mkdir()
    data_dir.mkdir()
    output_dir.mkdir()
    other_cwd.mkdir()

    base_config = config_dir / "base.yaml"
    child_config = config_dir / "child.yaml"
    boundary_path = data_dir / "boundary.gpkg"
    boundary_path.touch()

    base_config.write_text(
        "\n".join(
                [
                    "study_area:",
                    "  commune_name: Test",
                    "  commune_insee: '00000'",
                    "  boundary_path: ../data/boundary.gpkg",
                    "  boundary_layer: commune",
                    "  boundary_name_field: libelle",
                    "  boundary_name_value: Test",
                    "  department_code: '00'",
                    "  buffer_m: 0",
                    "data_paths:",
                    "  input:",
                    "    bd_topo: ../data/bd_topo.gpkg",
                    "    bd_topo_layer: batiment",
                    "    bdnb: ../data/bdnb.gpkg",
                    "    filosofi: ../data/filosofi.shp",
                    "    schools_csv: ../data/schools.csv",
                    "    tourism_restaurants: ../data/restaurants.csv",
                    "    tourism_hotels: ../data/hotels.csv",
                    "    tourism_campings: ../data/campings.csv",
                    "    tourism_residences: ../data/residences.csv",
                    "    tourism_collective: ../data/collective.csv",
                    "    tourism_locative: ../data/locative.csv",
                    "    beaches_raw: ../data/beaches.shp",
                    "    tourism_capacity_insee: ../data/capacity.zip",
                    "    audit_restaurants: ../data/audit.csv",
                    "  output:",
                    "    interim_dir: ../out",
                    "    final_export: ../out/result.gpkg",
                    "non_residential_model:",
                "  accommodation:",
                "    enabled: false",
                "    evidence: {}",
                "  activities:",
                "    enabled: false",
                "    evidence: {}",
                "  beaches:",
                "    enabled: false",
                "    evidence: {}",
            ]
        ),
        encoding="utf-8",
    )
    child_config.write_text(
        "\n".join(
                [
                    "extends: base.yaml",
                    "scenario:",
                    "  name: test",
                    "  day_of_week: Jeudi",
                    "  is_school_holiday: false",
                    "  reference_hour: 10",
                    "  residences:",
                    "    r_rp: 0.3",
                    "    r_rs: 0.6",
                    "    tau_saison: 0.1",
                    "    alpha_domicile: 0.7",
                    "  commerce:",
                    "    sqm_per_employee: 30",
                    "    client_employee_ratio: 4",
                    "    alpha_commerce: 0.0",
                    "  tourisme:",
                    "    tau_meteo: 0.2",
                    "    alpha_plage: 0.0",
                    "    tau_occupation_lits: 0.1",
                    "  temporal_context:",
                    "    season: winter",
                    "    weather_index: 0.2",
                    "    alert_level: 0.0",
                    "    religious_day: false",
                ]
            ),
            encoding="utf-8",
    )

    monkeypatch.chdir(other_cwd)
    config = load_config(child_config, require_complete_validation=False)

    assert Path(config["study_area"]["boundary_path"]) == boundary_path.resolve()
    assert Path(config["data_paths"]["output"]["final_export"]) == (output_dir / "result.gpkg").resolve()


def test_load_config_resolves_paths_per_extends_layer(tmp_path):
    root_dir = tmp_path / "root"
    config_dir = root_dir / "config"
    scenarios_dir = config_dir / "scenarios"
    validation_dir = config_dir / "validation"
    data_dir = root_dir / "data"
    root_dir.mkdir()
    config_dir.mkdir()
    scenarios_dir.mkdir()
    validation_dir.mkdir()
    data_dir.mkdir()

    (data_dir / "boundary.gpkg").touch()
    (data_dir / "result.gpkg").touch()

    (config_dir / "base.yaml").write_text(
        "\n".join(
                [
                    "study_area:",
                    "  commune_name: Test",
                    "  commune_insee: '00000'",
                    "  boundary_path: ../data/boundary.gpkg",
                    "  boundary_layer: commune",
                    "  boundary_name_field: libelle",
                    "  boundary_name_value: Test",
                    "  department_code: '00'",
                    "  buffer_m: 0",
                    "data_paths:",
                    "  input:",
                    "    bd_topo: ../data/bd_topo.gpkg",
                    "    bd_topo_layer: batiment",
                    "    bdnb: ../data/bdnb.gpkg",
                    "    filosofi: ../data/filosofi.shp",
                    "    schools_csv: ../data/schools.csv",
                    "    tourism_restaurants: ../data/restaurants.csv",
                    "    tourism_hotels: ../data/hotels.csv",
                    "    tourism_campings: ../data/campings.csv",
                    "    tourism_residences: ../data/residences.csv",
                    "    tourism_collective: ../data/collective.csv",
                    "    tourism_locative: ../data/locative.csv",
                    "    beaches_raw: ../data/beaches.shp",
                    "    tourism_capacity_insee: ../data/capacity.zip",
                    "    audit_restaurants: ../data/audit.csv",
                    "  output:",
                    "    interim_dir: ../data",
                    "    final_export: ../data/result.gpkg",
                    "non_residential_model:",
                "  accommodation:",
                "    enabled: false",
                "    evidence: {}",
                "  activities:",
                "    enabled: false",
                "    evidence: {}",
                "  beaches:",
                "    enabled: false",
                "    evidence: {}",
            ]
        ),
        encoding="utf-8",
    )
    (validation_dir / "proxies.yaml").write_text(
        "\n".join(
            [
                "extends: ../base.yaml",
            ]
        ),
        encoding="utf-8",
    )
    child_config = scenarios_dir / "day.yaml"
    child_config.write_text(
        "\n".join(
                [
                    "extends: ../validation/proxies.yaml",
                    "scenario:",
                    "  name: test",
                    "  day_of_week: Jeudi",
                    "  is_school_holiday: false",
                    "  reference_hour: 10",
                    "  residences:",
                    "    r_rp: 0.3",
                    "    r_rs: 0.6",
                    "    tau_saison: 0.1",
                    "    alpha_domicile: 0.7",
                    "  commerce:",
                    "    sqm_per_employee: 30",
                    "    client_employee_ratio: 4",
                    "    alpha_commerce: 0.0",
                    "  tourisme:",
                    "    tau_meteo: 0.2",
                    "    alpha_plage: 0.0",
                    "    tau_occupation_lits: 0.1",
                    "  temporal_context:",
                    "    season: winter",
                    "    weather_index: 0.2",
                    "    alert_level: 0.0",
                    "    religious_day: false",
                ]
            ),
            encoding="utf-8",
    )

    config = load_config(child_config, require_complete_validation=False)

    assert Path(config["study_area"]["boundary_path"]) == (data_dir / "boundary.gpkg").resolve()
    assert Path(config["data_paths"]["output"]["final_export"]) == (data_dir / "result.gpkg").resolve()


def test_load_config_detects_extends_cycle(tmp_path):
    config_a = tmp_path / "a.yaml"
    config_b = tmp_path / "b.yaml"
    config_a.write_text("extends: b.yaml\n", encoding="utf-8")
    config_b.write_text("extends: a.yaml\n", encoding="utf-8")

    with pytest.raises(ValueError, match="Boucle detectee"):
        load_config(config_a, require_complete_validation=False)


def test_load_config_rejects_missing_input_path_even_with_valid_schema(tmp_path):
    missing_bd_topo = tmp_path / "does_not_exist.gpkg"
    child_config = tmp_path / "child_missing_path.yaml"
    base_config = Path("config.yaml").resolve()
    child_config.write_text(
        "\n".join(
            [
                f"extends: {base_config}",
                "data_paths:",
                "  input:",
                f"    bd_topo: {missing_bd_topo}",
            ]
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="data_paths.input.bd_topo"):
        load_config(child_config)


def test_load_config_allows_missing_boundary_when_network_fallback_enabled(tmp_path):
    missing_boundary = tmp_path / "missing_boundary.gpkg"
    child_config = tmp_path / "child_network_fallback.yaml"
    base_config = Path("config.yaml").resolve()
    child_config.write_text(
        "\n".join(
            [
                f"extends: {base_config}",
                "study_area:",
                f"  boundary_path: {missing_boundary}",
                "  allow_network_fallback: true",
            ]
        ),
        encoding="utf-8",
    )

    config = load_config(child_config)
    assert config["study_area"]["allow_network_fallback"] is True


def test_validate_config_for_evidence_rejects_invalid_escort_scoring():
    config = {
        'project': {
            'name': 'x',
            'crs_epsg': 2154,
            'random_seed': 123,
            'building_id': {'prefix': 'BATZ', 'source_priority': ['cleabs']},
        },
        'study_area': {
            'commune_name': 'Test',
            'commune_insee': '00000',
            'boundary_path': '/tmp/boundary.gpkg',
            'boundary_layer': 'commune',
            'boundary_name_field': 'libelle',
            'boundary_name_value': 'Test',
            'department_code': '00',
            'buffer_m': 0,
        },
        'data_paths': {
            'input': {
                'bd_topo': '/tmp/a',
                'bd_topo_layer': 'batiment',
                'bdnb': '/tmp/b',
                'filosofi': '/tmp/c',
                'schools_csv': '/tmp/d',
                'tourism_restaurants': '/tmp/e',
                'tourism_hotels': '/tmp/f',
                'tourism_campings': '/tmp/g',
                'tourism_residences': '/tmp/h',
                'tourism_collective': '/tmp/i',
                'tourism_locative': '/tmp/j',
                'beaches_raw': '/tmp/k',
                'tourism_capacity_insee': '/tmp/l',
                'audit_restaurants': '/tmp/m',
            },
            'output': {'interim_dir': '/tmp/out', 'final_export': '/tmp/out/final.gpkg'},
        },
        'external_preparation': {'output_dir': '/tmp/out', 'accommodation': {'match_max_distance_m': 120, 'preferred_usage_any_of': ['Résidentiel'], 'capacity_rules': {'hotel_beds_per_room': 1.0, 'residence_beds_per_room': 2.0, 'camping_persons_per_pitch': 1.0}}, 'beaches': {'line_buffer_m': 15.0}},
        'visualization': {'destination_flows': {'output_path': '/tmp/out/x.png', 'min_flow_count': 1, 'top_destination_types': 5, 'top_destination_buildings': 5, 'annotate_top_destinations': 3, 'flow_width_scale': 0.2, 'figure_size': [10, 6]}},
        'filtering': {'min_building_area_m2': 1.0, 'fallback_sqm_per_dwelling': 80.0},
        'demographics': {
            'age_pyramid': {'under_15': 0.1, 'from_15_to_64': 0.6, 'over_65': 0.3},
            'employment': {'total_emplois_lieu_travail': 100, 'travail_local_pct': 0.4, 'navetteurs_ext_pct': 0.6},
            'households': {
                'enforce_exact_role_targets': True,
                'size_distribution': {'1': 0.5, '2': 0.5},
                'family_household_pct': 0.3,
                'child_household_adult_min': 1,
                'two_adults_if_children_pct': 0.6,
                'single_senior_pct': 0.4,
                'family_guardian': {'actif_local_pct': 0.4, 'actif_navetteur_pct': 0.5, 'senior_pct': 0.1},
            },
        },
        'destination_model': {
            'fallback_destination': 'EXTERIEUR',
            'default_max_distance_m': 1000,
            'min_distance_m': 0,
            'distance_decay': 1.0,
            'role_pools': {
                'scolaire': {'usage_any_of': ['Enseignement'], 'max_distance_m': 1000, 'distance_decay': 1.0},
                'actif_local': {'usage_any_of': ['Commercial et services'], 'max_distance_m': 1000, 'distance_decay': 1.0},
            },
        },
        'temporal_model': {
            'calendars': {'weekend_days': ['Samedi', 'Dimanche']},
            'scenario_context': {'season': 'winter', 'weather_index': 0.2, 'alert_level': 0.2, 'religious_day': False},
            'modifiers': {
                'leisure_weather_sensitivity': 0.5,
                'leisure_alert_sensitivity': 0.5,
                'restaurant_weather_sensitivity': 0.3,
                'restaurant_alert_sensitivity': 0.3,
                'activity_weather_sensitivity': 0.3,
                'activity_alert_sensitivity': 0.3,
            },
            'household_dynamics': {
                'enable_school_escort': True,
                'school_walk_max_distance_m': 1000,
                'school_pickup_overlap_hours': 1,
                'escort_scoring': {
                    'role_weights': {'senior': -1.0, 'inactif': 1.0, 'actif_local': 1.0, 'actif_navetteur': 1.0},
                    'proximity': {'max_score': 10.0, 'distance_scale_m': 250.0},
                    'pickup': {'bonus_if_possible': 10.0, 'bonus_if_not_possible': 1.0},
                    'departure_alignment': {'bonus_if_no_departure': 2.0, 'max_bonus_if_departure_after_child': 3.0},
                },
            },
            'role_profiles': {'scolaire': {}, 'actif_local': {}, 'actif_navetteur': {}, 'senior': {}},
        },
        'poi_matching': {'restaurants': {'max_distance_m': 80, 'preferred_usage_any_of': ['Résidentiel'], 'allow_fallback_any_usage': True, 'concat_multiple_names': True, 'evidence': {}}},
        'non_residential_model': {
            'accommodation': {'enabled': False, 'evidence': {}},
            'activities': {'enabled': False, 'evidence': {}},
            'beaches': {'enabled': False, 'evidence': {}},
        },
        'infrastructures': {
            'schools': {'s1': {'capacity': 10, 'name': 'A', 'latitude': 0.0, 'longitude': 0.0}},
            'school_matching': {'match_max_distance_m': 120},
            'schedules': {'school_default_start': '08:30', 'school_default_end': '16:30'},
        },
        'scenario': {
            'name': 'test',
            'day_of_week': 'Jeudi',
            'is_school_holiday': False,
            'reference_hour': 10,
            'residences': {'r_rp': 0.3, 'r_rs': 0.5, 'tau_saison': 0.1, 'alpha_domicile': 0.7},
            'commerce': {'sqm_per_employee': 30, 'client_employee_ratio': 4, 'alpha_commerce': 0.2},
            'tourisme': {'tau_meteo': 0.2, 'alpha_plage': 0.1, 'tau_occupation_lits': 0.2},
            'temporal_context': {'season': 'winter', 'weather_index': 0.2, 'alert_level': 0.0, 'religious_day': False},
        },
        'proxy_validation': {'scenario_sets': {'default': [{'config_path': '/tmp/x.yaml'}]}, 'temporal_proxies': []},
    }

    with pytest.raises(ValueError, match='escort_scoring.role_weights.senior'):
        validate_config_for_evidence(config, require_complete=True)
