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


def test_load_config_supports_extends():
    config = load_config(Path("config_summer_day.yaml"))

    assert config['scenario']['name'] == "summer_weekday_day"
    assert config['scenario']['temporal_context']['season'] == "summer"
    assert config['data_paths']['output']['final_export'] == "data/03_processed/population_batz_t0.gpkg"
