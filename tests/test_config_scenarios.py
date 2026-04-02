from pathlib import Path

import pytest

from src.pipeline import load_config


SCENARIOS = [
    ("config.yaml", "xynthia_winter_night_02h"),
    ("config_weekday_school_day.yaml", "weekday_school_day_public_validation"),
    ("config_summer_day.yaml", "summer_weekday_day"),
    ("config/scenarios/xynthia_winter_night.yaml", "xynthia_winter_night_02h"),
    ("config/scenarios/weekday_school_day.yaml", "weekday_school_day_public_validation"),
    ("config/scenarios/summer_day.yaml", "summer_weekday_day"),
]


@pytest.mark.parametrize(("config_path", "expected_name"), SCENARIOS)
def test_scenario_configs_keep_minimal_structure(config_path: str, expected_name: str):
    config = load_config(config_path)

    assert config["scenario"]["name"] == expected_name
    assert "household_dynamics" in config["temporal_model"]
    assert "role_profiles" in config["temporal_model"]
    assert config["proxy_validation"]["temporal_proxies"]
    assert config["proxy_validation"]["scenario_sets"]["default"]
    assert Path(config["study_area"]["boundary_path"]).name == "referentiel_administratif.gpkg"
    assert Path(config["data_paths"]["output"]["final_export"]).name == "population_batz_t0.gpkg"


def test_proxy_validation_scenario_set_points_to_existing_structured_scenarios():
    config = load_config("config.yaml")
    scenario_sets = config["proxy_validation"]["scenario_sets"]

    for scenario_specs in scenario_sets.values():
        for spec in scenario_specs:
            scenario_path = Path(spec["config_path"])
            assert scenario_path.exists()
            assert "config/scenarios/" in str(scenario_path)
