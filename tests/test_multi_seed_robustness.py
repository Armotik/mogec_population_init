from __future__ import annotations

from copy import deepcopy

import geopandas as gpd
import numpy as np
from shapely.geometry import Polygon

from src.core.proxy_validation import evaluate_temporal_proxies
from src.core.temporal import generer_matrice_horaire


def _seed_base_config() -> dict:
    return {
        "scenario": {
            "name": "multi_seed_robustness",
            "day_of_week": "Jeudi",
            "is_school_holiday": False,
            "temporal_context": {},
        },
        "project": {"random_seed": 0},
        "temporal_model": {
            "calendars": {"weekend_days": ["Samedi", "Dimanche"]},
            "scenario_context": {"weather_index": 1.0, "alert_level": 0.0, "religious_day": False},
            "modifiers": {
                "leisure_weather_sensitivity": 0.0,
                "leisure_alert_sensitivity": 0.0,
                "restaurant_weather_sensitivity": 0.0,
                "restaurant_alert_sensitivity": 0.0,
                "activity_weather_sensitivity": 0.0,
                "activity_alert_sensitivity": 0.0,
            },
            "household_dynamics": {
                "enable_school_escort": False,
                "school_walk_max_distance_m": 1200,
                "school_pickup_overlap_hours": 1,
            },
            "role_profiles": {
                "senior": {
                    "weekday": {
                        "market_probability": 0.0,
                        "market_hours": [],
                        "midday_restaurant_probability": 0.0,
                        "midday_restaurant_hours": [],
                        "afternoon_out_probability": 0.55,
                        "afternoon_out_hours": [15, 16],
                        "evening_restaurant_probability": 0.0,
                        "evening_restaurant_hours": [],
                    }
                }
            },
        },
        "proxy_validation": {
            "temporal_proxies": [
                {
                    "proxy_id": "senior_outside_share_seed_campaign",
                    "metric": "role_state_share",
                    "role": "senior",
                    "state": "exterieur",
                    "comparison_normalization": "none",
                    "reference_curve": [0.0] * 24,
                    "thresholds": {
                        "correlation_pass_min": -1.0,
                        "correlation_warn_min": -1.0,
                        "rmse_pass_max": 10.0,
                        "rmse_warn_max": 10.0,
                        "peak_gap_pass_max_hours": 23,
                        "peak_gap_warn_max_hours": 23,
                    },
                    "evidence": {
                        "formula": "Part_senior_exterieur(t)",
                        "source_name": "Campagne multi-seed synthetique",
                        "source_url": "https://example.org/seed-campaign",
                        "source_file": "",
                        "extraction_date": "2026-05-08",
                        "confidence": "medium",
                    },
                }
            ]
        },
    }


def _seed_base_gdf() -> gpd.GeoDataFrame:
    return gpd.GeoDataFrame(
        {
            "building_id": ["HOME"],
            "usage_1": ["Résidentiel"],
            "pop_t0": [1],
            "households": [
                [
                    {
                        "household_id": "HH1",
                        "guardian_member_id": None,
                        "members": [{"member_id": "senior_1", "role": "senior", "destination_id": "DOMICILE"}],
                    }
                ]
            ],
        },
        geometry=[Polygon([(0, 0), (0, 10), (10, 10), (10, 0)])],
        crs="EPSG:2154",
    )


def test_campaign_multi_seed_proxy_and_invariants():
    base_config = _seed_base_config()
    base_gdf = _seed_base_gdf()

    seed_values = list(range(1000, 1100))
    h15_values: list[float] = []
    h16_values: list[float] = []

    for seed in seed_values:
        config = deepcopy(base_config)
        config["project"]["random_seed"] = seed
        gdf_model = generer_matrice_horaire(base_gdf.copy(), config)
        summary, curves = evaluate_temporal_proxies(gdf_model, config)

        assert len(summary) == 1
        assert not curves.empty
        assert np.isfinite(summary["rmse"].iloc[0])
        assert np.isfinite(summary["mae"].iloc[0])
        assert np.isfinite(summary["correlation"].iloc[0])

        for hour in range(24):
            value = int(gdf_model[f"pop_h{hour}"].sum())
            assert 0 <= value <= 1

        selected = curves[curves["proxy_id"] == "senior_outside_share_seed_campaign"].sort_values("hour")
        h15_values.append(float(selected.loc[selected["hour"] == 15, "modeled_value"].iloc[0]))
        h16_values.append(float(selected.loc[selected["hour"] == 16, "modeled_value"].iloc[0]))

    h15_array = np.array(h15_values, dtype=float)
    h16_array = np.array(h16_values, dtype=float)

    assert h15_array.min() == 0.0 and h15_array.max() == 1.0
    assert h16_array.min() == 0.0 and h16_array.max() == 1.0

    mean_h15 = float(h15_array.mean())
    mean_h16 = float(h16_array.mean())
    assert 0.35 <= mean_h15 <= 0.75
    assert 0.35 <= mean_h16 <= 0.75
