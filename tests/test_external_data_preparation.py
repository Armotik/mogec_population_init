import geopandas as gpd
from shapely.geometry import Point, Polygon

from src.io.external_data_preparation import (
    prepare_accommodation_capacity_table,
    prepare_restaurants_table,
)


def _base_external_config() -> dict:
    return {
        "project": {
            "crs_epsg": 2154,
            "building_id": {"prefix": "TEST"},
        },
        "study_area": {
            "commune_name": "Batz-sur-Mer, Loire-Atlantique, France",
            "commune_insee": "44010",
        },
        "external_preparation": {
            "accommodation": {
                "capacity_rules": {
                    "hotel_beds_per_room": 2.0,
                    "residence_beds_per_room": 2.0,
                    "camping_persons_per_pitch": 2.5,
                },
                "match_max_distance_m": 150.0,
                "preferred_usage_any_of": ["Résidentiel", "Commercial"],
            }
        },
        "non_residential_model": {
            "accommodation": {
                "double_count_prevention": {
                    "residential_usage_any_of": ["Résidentiel"],
                    "exclude_source_types_on_residential": ["locative"],
                    "warn_source_types_on_residential": ["residence"],
                }
            }
        },
        "data_paths": {
            "input": {
                "bd_topo": "",
                "bd_topo_layer": "",
            }
        },
        "filtering": {"min_building_area_m2": 9},
    }


def test_prepare_restaurants_table_formats_expected_columns():
    restaurants = gpd.GeoDataFrame(
        {
            "dataset_name": ["restaurants"],
            "dataset_type": ["restaurant"],
            "offer_name": ["Le Test"],
            "commune_name": ["Batz-sur-Mer"],
            "commune_insee": ["44010"],
            "address": ["1 rue du Port"],
            "website": ["https://example.org"],
            "opening_hours_raw": ["Mo-Su 12:00-22:00"],
        },
        geometry=gpd.GeoSeries.from_xy([ -2.48 ], [47.277], crs="EPSG:4326").to_crs("EPSG:2154"),
        crs="EPSG:2154",
    )

    table = prepare_restaurants_table(restaurants)

    assert list(table.columns) == [
        "nom",
        "lat",
        "lon",
        "opening_hours_brut",
        "horaire_ouverture",
        "horaire_fermeture",
        "commune",
        "code_insee",
        "address",
        "website",
        "source_dataset",
    ]
    assert table.iloc[0]["nom"] == "Le Test"
    assert table.iloc[0]["commune"] == "Batz-sur-Mer"
    assert table.iloc[0]["code_insee"] == "44010"
    assert abs(float(table.iloc[0]["lat"]) - 47.277) < 1e-3
    assert abs(float(table.iloc[0]["lon"]) + 2.48) < 1e-3


def test_prepare_accommodation_capacity_table_aggregates_matched_offers(monkeypatch):
    config = _base_external_config()

    accommodation = gpd.GeoDataFrame(
        {
            "dataset_type": ["hotel", "locative"],
            "offer_name": ["Hotel A", "Maison B"],
            "commune_name": ["Batz-sur-Mer", "Batz-sur-Mer"],
            "commune_insee": ["44010", "44010"],
            "address": ["1 rue A", "2 rue B"],
            "website": ["https://hotel.test", "https://locative.test"],
            "capacity_rooms": [10, None],
            "capacity_persons": [None, 4],
            "capacity_beds": [None, None],
            "capacity_units": [None, None],
            "capacity_pitches": [None, None],
        },
        geometry=gpd.GeoSeries(
            [Point(0, 0), Point(2, 2)],
            crs="EPSG:2154",
        ),
        crs="EPSG:2154",
    )

    buildings = gpd.GeoDataFrame(
        {
            "building_id": ["BAT1"],
            "usage_1": ["Résidentiel"],
        },
        geometry=[Polygon([(-10, -10), (-10, 10), (10, 10), (10, -10)])],
        crs="EPSG:2154",
    )

    monkeypatch.setattr(
        "src.io.external_data_preparation._load_buildings_for_matching",
        lambda config: buildings,
    )

    capacity = prepare_accommodation_capacity_table(accommodation, config)

    assert len(capacity) == 1
    assert capacity.iloc[0]["building_id"] == "BAT1"
    assert int(capacity.iloc[0]["capacity_lits"]) == 24
    assert capacity.iloc[0]["offer_count"] == 2
    assert capacity.iloc[0]["source_types"] == "hotel | locative"
    assert capacity.iloc[0]["offer_names"] == "Hotel A | Maison B"
