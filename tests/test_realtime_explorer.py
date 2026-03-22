import geopandas as gpd
from shapely.geometry import Polygon

from src.visualization.realtime_explorer import (
    _classify_rebuild_mode,
    _diff_config_paths,
    apply_config_updates,
    apply_yaml_patch,
    build_realtime_explorer_payload,
    get_editable_config_fields,
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
    assert 'config_editor' in payload
    editable_paths = {field['path'] for field in payload['config_editor']['fields']}
    assert 'scenario.day_of_week' in editable_paths
    assert 'temporal_model.household_dynamics.school_walk_max_distance_m' in editable_paths
    child = next(member for member in payload['members'] if member['member_id'] == 'child')
    assert child['school_access_status'] == 'escort'
    assert child['timeline_points'][8] is not None


def test_realtime_explorer_html_mentions_satellite_and_api():
    html = render_realtime_explorer_html()

    assert 'Explorateur temps reel' in html
    assert 'satellite' in html.lower()
    assert '/api/state' in html
    assert '/api/config' in html
    assert 'configPatchTextarea' in html
    assert 'map-tiles' in html
    assert 'function initMap()' in html
    assert '.map-tiles,' in html
    assert 'pointer-events: none;' in html
    assert 'configDraftYaml' in html
    assert 'spellcheck="false"' in html
    assert 'autocapitalize="none"' in html
    assert "configPatchTextarea.addEventListener('input'" in html
    assert "configPatchTextarea.addEventListener('change'" in html
    assert "configPatchTextarea.addEventListener('blur'" in html


def test_editable_config_fields_and_updates():
    config = {
        'scenario': {
            'day_of_week': 'Jeudi',
            'is_school_holiday': False,
            'reference_hour': 2,
            'residences': {'alpha_domicile': 0.95},
        },
        'temporal_model': {
            'scenario_context': {'weather_index': 0.2, 'alert_level': 0.8},
            'household_dynamics': {
                'school_walk_max_distance_m': 1200,
                'school_pickup_overlap_hours': 1,
            },
        },
        'non_residential_model': {
            'accommodation': {'tau_occupation': 0.10},
        },
    }

    fields = get_editable_config_fields(config)
    values_by_path = {field['path']: field['value'] for field in fields}
    assert values_by_path['scenario.day_of_week'] == 'Jeudi'
    assert values_by_path['scenario.temporal_context.weather_index'] == 0.2

    updated = apply_config_updates(
        config,
        {
            'scenario.day_of_week': 'Dimanche',
            'scenario.is_school_holiday': True,
            'scenario.temporal_context.weather_index': 0.9,
            'temporal_model.household_dynamics.school_walk_max_distance_m': 800,
        },
    )
    assert updated['scenario']['day_of_week'] == 'Dimanche'
    assert updated['scenario']['is_school_holiday'] is True
    assert updated['scenario']['temporal_context']['weather_index'] == 0.9
    assert updated['temporal_model']['household_dynamics']['school_walk_max_distance_m'] == 800

    yaml_updated = apply_yaml_patch(
        config,
        """
scenario:
  day_of_week: "Dimanche"
  temporal_context:
    alert_level: 0.3
""",
    )
    assert yaml_updated['scenario']['day_of_week'] == 'Dimanche'
    assert yaml_updated['scenario']['temporal_context']['alert_level'] == 0.3


def test_rebuild_mode_classification():
    before = {
        'scenario': {
            'reference_hour': 2,
            'day_of_week': 'Jeudi',
            'temporal_context': {'weather_index': 0.2},
            'residences': {'alpha_domicile': 0.95},
        },
        'temporal_model': {
            'household_dynamics': {'school_walk_max_distance_m': 1200},
        },
    }

    after_reference = {
        **before,
        'scenario': {
            **before['scenario'],
            'reference_hour': 8,
        },
    }
    changed_reference = _diff_config_paths(before, after_reference)
    assert _classify_rebuild_mode(changed_reference, has_cached_gdf=True) == 'payload_only'

    after_temporal = {
        **before,
        'scenario': {
            **before['scenario'],
            'day_of_week': 'Dimanche',
        },
    }
    changed_temporal = _diff_config_paths(before, after_temporal)
    assert _classify_rebuild_mode(changed_temporal, has_cached_gdf=True) == 'temporal_only'

    after_structural = {
        **before,
        'scenario': {
            **before['scenario'],
            'residences': {'alpha_domicile': 0.75},
        },
    }
    changed_structural = _diff_config_paths(before, after_structural)
    assert _classify_rebuild_mode(changed_structural, has_cached_gdf=True) == 'full'
