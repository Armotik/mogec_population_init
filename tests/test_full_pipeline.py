import pytest
from src.io.exporters import exporter_pour_gama
from src.pipeline import run_pipeline


def test_full_pipeline_execution(config):
    pop_temporelle = run_pipeline(config)
    path_final = exporter_pour_gama(pop_temporelle, config)

    assert path_final.exists()
    assert 'building_id' in pop_temporelle.columns
    assert 'is_restaurant' in pop_temporelle.columns
    assert 'is_culte' in pop_temporelle.columns
    print(f"\n[PIPELINE OK] Le fichier est prêt pour GAMA : {path_final}")
