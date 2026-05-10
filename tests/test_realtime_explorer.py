from pathlib import Path

import geopandas as gpd
import pandas as pd
from shapely.geometry import Polygon

from src.visualization import realtime_explorer
from src.visualization.realtime_explorer import (
    _ExplorerState,
    _make_json_safe,
    build_realtime_explorer_payload,
    render_realtime_explorer_html,
)


def test_realtime_explorer_payload_contains_households_and_school_access():
    config = {
        'scenario': {
            'name': 'test_web',
            'day_of_week': 'Jeudi',
            'is_school_holiday': False,
            'reference_hour': 2,
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

    payload = build_realtime_explorer_payload(gdf, config)

    assert payload['scenario_name'] == 'test_web'
    assert payload['reference_hour'] == 2
    assert len(payload['households']) == 1
    assert payload['households'][0]['household_id'] == 'HH1'
    assert payload['households'][0]['escort_children_count'] == 1
    assert 'hourly_place_presence' in payload
    assert len(payload['hourly_place_presence']) == 24
    assert 'map_places' in payload
    assert 'map_exogenous_places' in payload
    assert 'proxy_validation' in payload
    assert payload['proxy_validation']['active_proxy_count'] == 0
    child = next(member for member in payload['members'] if member['member_id'] == 'child')
    assert child['school_access_status'] == 'escort'
    assert child['timeline_points'][8] is not None


def test_realtime_explorer_html_mentions_satellite_and_api():
    html = render_realtime_explorer_html()

    assert 'Lecture interactive du scenario' in html
    assert 'satellite' in html.lower()
    assert '/api/state' in html
    assert '/api/scenario' in html
    assert 'scenarioSelect' in html
    assert 'proxySelect' in html
    assert 'proxyStatusFilter' in html
    assert 'proxyListPanel' in html
    assert 'proxyChart' in html
    assert '/api/proxy-compare' in html
    assert 'proxyComparisonSetSelect' in html
    assert 'proxyComparisonChart' in html
    assert 'loadProxyComparisonButton' in html
    assert 'exportProxyComparisonButton' in html
    assert 'exportProxySummaryButton' in html
    assert 'exportProxyCurvesButton' in html
    assert 'fetchJsonOrThrow' in html
    assert 'Chargement du scenario...' in html
    assert 'Comparaison non lancee pour cette selection.' in html
    assert 'Matrice horaire' in html
    assert 'matrix-table' in html
    assert '/[",\\n]/.test(stringValue)' in html
    assert "lines.join('\\n')" in html
    assert 'map-tiles' in html
    assert 'function initMap()' in html
    assert '.map-tiles,' in html
    assert 'pointer-events: none;' in html
    assert 'configPatchTextarea' not in html
    assert '/api/config' not in html


def test_compare_proxy_loads_scenario_from_explicit_config_path(monkeypatch, tmp_path):
    root_config = tmp_path / "config.yaml"
    scenario_dir = tmp_path / "config" / "scenarios"
    scenario_dir.mkdir(parents=True)
    contrast_config = scenario_dir / "summer_day.yaml"
    root_config.write_text("scenario: {}\n", encoding="utf-8")
    contrast_config.write_text("scenario: {}\n", encoding="utf-8")

    current_config = {
        "scenario": {"name": "scenario_courant"},
        "proxy_validation": {
            "scenario_sets": {
                "contrast": [
                    {
                        "config_path": "config/scenarios/summer_day.yaml",
                        "label": "ete_jour_vacances",
                    }
                ]
            }
        },
    }
    contrast_loaded_config = {"scenario": {"name": "scenario_ete"}}

    def fake_discover_root_scenarios(root_dir: Path, initial_config_path: str | Path | None = None) -> list[dict[str, str]]:
        return [
            {
                "id": "config.yaml",
                "file_name": "config.yaml",
                "scenario_name": "scenario_courant",
                "label": "scenario_courant (config.yaml)",
                "config_path": str(root_config.resolve()),
            }
        ]

    def fake_load_config(path: str | Path) -> dict:
        resolved = Path(path).resolve()
        if resolved == root_config.resolve():
            return current_config
        if resolved == contrast_config.resolve():
            return contrast_loaded_config
        raise AssertionError(f"Chemin inattendu: {resolved}")

    def fake_run_pipeline(config: dict) -> str:
        return str(config["scenario"]["name"])

    def fake_evaluate_temporal_proxies(gdf_model: str, config: dict) -> tuple[pd.DataFrame, pd.DataFrame]:
        scenario_name = str(config["scenario"]["name"])
        summary_df = pd.DataFrame(
            [
                {
                    "scenario_name": scenario_name,
                    "proxy_id": "proxy_demo",
                    "label": "Proxy demo",
                    "metric": "role_state_share",
                    "applicable": True,
                    "status": "pass",
                    "reason": "evaluated",
                    "correlation": 0.91,
                    "rmse": 0.08,
                    "mae": 0.05,
                    "peak_hour_gap": 1,
                    "source_name": "Source test",
                    "extraction_date": "2026-04-03",
                    "confidence": "high",
                }
            ]
        )
        curves_df = pd.DataFrame(
            [
                {
                    "scenario_name": scenario_name,
                    "proxy_id": "proxy_demo",
                    "label": "Proxy demo",
                    "metric": "role_state_share",
                    "hour": hour,
                    "modeled_value": float(hour),
                    "reference_value": float(hour + 1),
                    "modeled_compared": float(hour),
                    "reference_compared": float(hour + 1),
                }
                for hour in range(24)
            ]
        )
        return summary_df, curves_df

    monkeypatch.setattr(realtime_explorer, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(realtime_explorer, "discover_root_scenarios", fake_discover_root_scenarios)
    monkeypatch.setattr(realtime_explorer, "load_config", fake_load_config)
    monkeypatch.setattr(realtime_explorer, "run_pipeline", fake_run_pipeline)
    monkeypatch.setattr(realtime_explorer, "evaluate_temporal_proxies", fake_evaluate_temporal_proxies)

    state = _ExplorerState(root_config)
    comparison = state.compare_proxy("proxy_demo", "contrast")

    assert comparison["set_id"] == "contrast"
    assert comparison["proxy_id"] == "proxy_demo"
    assert len(comparison["scenarios"]) == 1
    assert comparison["scenarios"][0]["scenario_name"] == "ete_jour_vacances"
    assert comparison["scenarios"][0]["scenario_file"] == "summer_day.yaml"
    assert len(comparison["reference_curve_rows"]) == 24


def test_make_json_safe_replaces_non_finite_numbers():
    payload = {
        "ok": 1,
        "nan_value": float("nan"),
        "nested": [float("inf"), {"neg_inf": float("-inf")}],
        "text": "stable",
    }

    safe = _make_json_safe(payload)

    assert safe["ok"] == 1
    assert safe["nan_value"] is None
    assert safe["nested"][0] is None
    assert safe["nested"][1]["neg_inf"] is None
    assert safe["text"] == "stable"
