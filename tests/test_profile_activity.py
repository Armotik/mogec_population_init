from pathlib import Path

import geopandas as gpd
from shapely.geometry import Polygon

from src.visualization.profile_activity import export_profile_activity_explorer


def test_export_profile_activity_explorer_creates_html(tmp_path):
    config = {
        'scenario': {
            'name': 'test_profile_explorer',
            'day_of_week': 'Jeudi',
            'is_school_holiday': False,
            'reference_hour': 2,
            'temporal_context': {},
        },
        'temporal_model': {
            'calendars': {'weekend_days': ['Samedi', 'Dimanche']},
            'scenario_context': {'weather_index': 1.0, 'alert_level': 0.0, 'religious_day': False},
            'modifiers': {},
            'household_dynamics': {'enable_school_escort': False},
            'role_profiles': {
                'scolaire': {
                    'weekday': {
                        'enabled': True,
                        'departure': {'mean': 8.0, 'std': 0.0, 'min': 8, 'max': 8},
                        'return': {'mean': 16.0, 'std': 0.0, 'min': 16, 'max': 16},
                    }
                },
                'senior': {'weekday': {}},
            },
        },
        'project': {'random_seed': 123},
    }

    gdf = gpd.GeoDataFrame(
        {
            'building_id': ['B1', 'B2'],
            'usage_1': ['Résidentiel', 'Enseignement'],
            'households': [
                [
                    {
                        'household_id': 'B1_hh1',
                        'members': [
                            {'member_id': 'm1', 'role': 'scolaire', 'destination_id': 'B2'},
                            {'member_id': 'm2', 'role': 'inactif', 'destination_id': 'DOMICILE'},
                        ],
                    }
                ],
                [],
            ],
        },
        geometry=[
            Polygon([(0, 0), (0, 10), (10, 10), (10, 0)]),
            Polygon([(20, 0), (20, 10), (30, 10), (30, 0)]),
        ],
        crs='EPSG:2154',
    )

    output = tmp_path / 'profile_activity_explorer.html'
    path = export_profile_activity_explorer(gdf, config, output)

    assert path.exists()
    content = Path(path).read_text(encoding='utf-8')
    assert 'Explorateur des profils et activites' in content
    assert 'm1' in content
