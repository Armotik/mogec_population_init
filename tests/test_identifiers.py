from src.core.geometry import filter_buildings_by_area
from src.core.identifiers import assign_building_ids


def test_assign_building_ids_is_stable_and_unique(bati_raw, config):
    bati_filtre = filter_buildings_by_area(bati_raw, config['filtering']['min_building_area_m2'])

    resultat_a = assign_building_ids(bati_filtre, config)
    resultat_b = assign_building_ids(bati_filtre, config)

    assert 'building_id' in resultat_a.columns
    assert 'building_id_source' in resultat_a.columns
    assert resultat_a['building_id'].is_unique
    assert resultat_a['building_id'].equals(resultat_b['building_id'])
    assert resultat_a['building_id'].str.startswith(config['project']['building_id']['prefix']).all()
