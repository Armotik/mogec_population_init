import pytest
import geopandas as gpd
from src.io.exporters import exporter_pour_gama


def test_full_pipeline_execution(config, bati_popule):
    pop_temporelle = bati_popule.copy()
    path_final = exporter_pour_gama(pop_temporelle, config)

    assert path_final.exists()
    assert 'building_id' in pop_temporelle.columns
    assert 'is_restaurant' in pop_temporelle.columns
    assert 'is_culte' in pop_temporelle.columns
    export_gdf = gpd.read_file(path_final)
    assert 'reference_hour' in export_gdf.columns
    assert int(export_gdf['reference_hour'].dropna().iloc[0]) == int(config['scenario'].get('reference_hour', 0))
    print(f"\n[PIPELINE OK] Le fichier est prêt pour GAMA : {path_final}")


def test_full_pipeline_scenario_reel_outside_commune_midday(member_timelines_weekday_school_day):
    outside_rows = member_timelines_weekday_school_day[
        (member_timelines_weekday_school_day['role'] == 'scolaire')
        & (member_timelines_weekday_school_day['school_access_status'] == 'outside_commune')
    ]

    assert len(outside_rows) > 0
    for _, row in outside_rows.iterrows():
        midday_destinations = [row['timeline_destinations'][hour] for hour in (9, 10, 11, 14, 15)]
        assert all(destination == 'EXTERIEUR' for destination in midday_destinations)
