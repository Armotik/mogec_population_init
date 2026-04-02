import geopandas as gpd
from shapely.geometry import Polygon

from src.core.proxy_validation import evaluate_temporal_proxies
from src.core.temporal import generer_matrice_horaire


def _base_proxy_config(is_school_holiday: bool = False) -> dict:
    return {
        "scenario": {
            "name": "proxy_test",
            "day_of_week": "Jeudi",
            "is_school_holiday": is_school_holiday,
            "temporal_context": {"season": "spring"},
        },
        "project": {"random_seed": 123},
        "temporal_model": {
            "calendars": {"weekend_days": ["Samedi", "Dimanche"]},
            "scenario_context": {"weather_index": 1.0, "alert_level": 0.0, "religious_day": False, "season": "spring"},
            "modifiers": {},
            "household_dynamics": {
                "enable_school_escort": False,
                "school_walk_max_distance_m": 500,
                "school_pickup_overlap_hours": 1,
            },
            "role_profiles": {
                "scolaire": {
                    "weekday": {
                        "enabled": not is_school_holiday,
                        "departure": {"mean": 8.0, "std": 0.0, "min": 8, "max": 8},
                        "return": {"mean": 16.0, "std": 0.0, "min": 16, "max": 16},
                    },
                    "holiday": {"enabled": False},
                },
                "actif_navetteur": {
                    "weekday": {
                        "enabled": True,
                        "departure": {"mean": 8.0, "std": 0.0, "min": 8, "max": 8},
                        "return": {"mean": 18.0, "std": 0.0, "min": 18, "max": 18},
                    }
                },
            },
        },
        "non_residential_model": {
            "activities": {"enabled": False},
            "beaches": {"enabled": False},
        },
    }


def _proxy_gdf() -> gpd.GeoDataFrame:
    return gpd.GeoDataFrame(
        {
            "building_id": ["HOME", "SCHOOL"],
            "usage_1": ["Résidentiel", "Enseignement"],
            "households": [
                [
                    {
                        "household_id": "HH1",
                        "guardian_member_id": None,
                        "members": [
                            {"member_id": "child", "role": "scolaire", "destination_id": "SCHOOL"},
                            {"member_id": "commuter", "role": "actif_navetteur", "destination_id": "EXTERIEUR"},
                        ],
                    }
                ],
                [],
            ],
        },
        geometry=[
            Polygon([(0, 0), (0, 10), (10, 10), (10, 0)]),
            Polygon([(100, 0), (100, 10), (110, 10), (110, 0)]),
        ],
        crs="EPSG:2154",
    )


def _hourly_binary_curve(start: int, end: int) -> list[float]:
    return [1.0 if start <= hour <= end else 0.0 for hour in range(24)]


def test_evaluate_temporal_proxies_returns_summary_and_curves():
    config = _base_proxy_config(is_school_holiday=False)
    config["proxy_validation"] = {
        "temporal_proxies": [
            {
                "proxy_id": "navetteurs_exterieur",
                "label": "Navetteurs hors commune",
                "metric": "role_state_share",
                "role": "actif_navetteur",
                "state": "exterieur",
                "comparison_normalization": "none",
                "reference_curve": _hourly_binary_curve(8, 18),
                "thresholds": {
                    "correlation_pass_min": 0.99,
                    "correlation_warn_min": 0.95,
                    "rmse_pass_max": 0.0,
                    "rmse_warn_max": 0.05,
                    "peak_gap_pass_max_hours": 0,
                    "peak_gap_warn_max_hours": 1,
                },
                "evidence": {
                    "formula": "Part_navetteurs_exterieur(t)",
                    "source_name": "Jeu synthetique de test",
                    "source_url": "https://example.org/navetteurs",
                    "source_file": "",
                    "extraction_date": "2026-03-24",
                    "confidence": "high",
                },
            },
            {
                "proxy_id": "presence_enseignement",
                "label": "Presence enseignement",
                "metric": "building_usage_share",
                "usage_any_of": ["Enseignement"],
                "comparison_normalization": "none",
                "reference_curve": _hourly_binary_curve(8, 16),
                "thresholds": {
                    "correlation_pass_min": 0.99,
                    "correlation_warn_min": 0.95,
                    "rmse_pass_max": 0.0,
                    "rmse_warn_max": 0.05,
                    "peak_gap_pass_max_hours": 0,
                    "peak_gap_warn_max_hours": 1,
                },
                "evidence": {
                    "formula": "Part_enseignement(t)",
                    "source_name": "Jeu synthetique de test",
                    "source_url": "https://example.org/enseignement",
                    "source_file": "",
                    "extraction_date": "2026-03-24",
                    "confidence": "high",
                },
            },
        ]
    }

    gdf = generer_matrice_horaire(_proxy_gdf(), config)
    summary, curves = evaluate_temporal_proxies(gdf, config)

    assert len(summary) == 2
    assert set(summary["status"]) == {"pass"}
    assert set(summary["proxy_id"]) == {"navetteurs_exterieur", "presence_enseignement"}
    assert len(curves) == 48

    schooling_curve = curves[curves["proxy_id"] == "presence_enseignement"].sort_values("hour")
    assert schooling_curve.loc[schooling_curve["hour"] == 9, "modeled_value"].iloc[0] == 1.0
    assert schooling_curve.loc[schooling_curve["hour"] == 3, "modeled_value"].iloc[0] == 0.0


def test_evaluate_temporal_proxies_can_normalize_on_internal_assigned_role_subset():
    config = _base_proxy_config(is_school_holiday=False)
    config["proxy_validation"] = {
        "temporal_proxies": [
            {
                "proxy_id": "scolaires_internes",
                "label": "Scolaires internes",
                "metric": "role_internal_assigned_state_share",
                "role": "scolaire",
                "state": "interne",
                "comparison_normalization": "none",
                "reference_curve": _hourly_binary_curve(8, 16),
                "thresholds": {
                    "correlation_pass_min": 0.99,
                    "correlation_warn_min": 0.95,
                    "rmse_pass_max": 0.0,
                    "rmse_warn_max": 0.05,
                    "peak_gap_pass_max_hours": 0,
                    "peak_gap_warn_max_hours": 1,
                },
                "evidence": {
                    "formula": "Part_scolaires_internes_assignes(t)",
                    "source_name": "Jeu synthetique de test",
                    "source_url": "https://example.org/scolaires-internes",
                    "source_file": "",
                    "extraction_date": "2026-03-24",
                    "confidence": "high",
                },
            }
        ]
    }

    gdf = generer_matrice_horaire(_proxy_gdf(), config)
    summary, curves = evaluate_temporal_proxies(gdf, config)

    assert summary.iloc[0]["status"] == "pass"
    assert curves.loc[curves["hour"] == 9, "modeled_value"].iloc[0] == 1.0
    assert curves.loc[curves["hour"] == 3, "modeled_value"].iloc[0] == 0.0


def test_evaluate_temporal_proxies_marks_non_applicable_proxy():
    config = _base_proxy_config(is_school_holiday=True)
    config["proxy_validation"] = {
        "temporal_proxies": [
            {
                "proxy_id": "presence_enseignement",
                "label": "Presence enseignement",
                "metric": "role_state_share",
                "role": "scolaire",
                "state": "interne",
                "comparison_normalization": "none",
                "reference_curve": _hourly_binary_curve(8, 16),
                "applicability": {"school_holidays": [False]},
                "evidence": {
                    "formula": "Part_scolaires_internes(t)",
                    "source_name": "Jeu synthetique de test",
                    "source_url": "https://example.org/school",
                    "source_file": "",
                    "extraction_date": "2026-03-24",
                    "confidence": "high",
                },
            }
        ]
    }

    gdf = generer_matrice_horaire(_proxy_gdf(), config)
    summary, curves = evaluate_temporal_proxies(gdf, config)

    assert len(summary) == 1
    assert bool(summary.iloc[0]["applicable"]) is False
    assert summary.iloc[0]["status"] == "info"
    assert "school_holiday_mismatch" in summary.iloc[0]["reason"]
    assert curves.empty
