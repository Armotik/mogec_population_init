import geopandas as gpd
from pyproj import Transformer
from shapely.geometry import Polygon

from src.core.schools import integrer_ecoles_aux_batiments


def test_integrer_ecoles_aux_batiments_reclassifies_best_candidates():
    transformer = Transformer.from_crs(4326, 2154, always_xy=True)
    school_a_x, school_a_y = transformer.transform(-2.4747162545043624, 47.27675018135515)
    school_b_x, school_b_y = transformer.transform(-2.4718651125187314, 47.27825566145671)

    gdf = gpd.GeoDataFrame(
        {
            "building_id": ["B1", "B2", "B3", "B4"],
            "usage_1": ["Résidentiel", "Commercial et services", "Commercial et services", "Résidentiel"],
            "surface_sol": [120.0, 900.0, 30.0, 140.0],
        },
        geometry=[
            Polygon([(school_a_x - 20, school_a_y - 5), (school_a_x - 20, school_a_y + 5), (school_a_x - 10, school_a_y + 5), (school_a_x - 10, school_a_y - 5)]),
            Polygon([(school_a_x + 5, school_a_y - 15), (school_a_x + 5, school_a_y + 15), (school_a_x + 35, school_a_y + 15), (school_a_x + 35, school_a_y - 15)]),
            Polygon([(school_b_x - 5, school_b_y - 3), (school_b_x - 5, school_b_y + 3), (school_b_x + 1, school_b_y + 3), (school_b_x + 1, school_b_y - 3)]),
            Polygon([(school_b_x + 12, school_b_y - 8), (school_b_x + 12, school_b_y + 8), (school_b_x + 22, school_b_y + 8), (school_b_x + 22, school_b_y - 8)]),
        ],
        crs="EPSG:2154",
    )

    config = {
        "infrastructures": {
            "schools": {
                "school_a": {
                    "name": "School A",
                    "capacity": 80,
                    "longitude": -2.4747162545043624,
                    "latitude": 47.27675018135515,
                },
                "school_b": {
                    "name": "School B",
                    "capacity": 60,
                    "longitude": -2.4718651125187314,
                    "latitude": 47.27825566145671,
                },
            },
            "school_matching": {
                "match_max_distance_m": 200,
                "min_building_area_m2": 80,
                "preferred_usage_any_of": ["Enseignement", "Commercial et services", "Indifférencié", "Résidentiel"],
            },
        }
    }

    result = integrer_ecoles_aux_batiments(gdf, config)

    school_rows = result[result["is_school"]]
    assert len(school_rows) == 2
    assert set(school_rows["building_id"]) == {"B2", "B4"}
    assert set(school_rows["usage_1"]) == {"Enseignement"}
    assert set(school_rows["school_capacity"]) == {80, 60}
    assert "Commercial et services" in result["usage_1_bdtopo"].tolist()


def test_integrer_ecoles_aux_batiments_without_coordinates_returns_input():
    gdf = gpd.GeoDataFrame(
        {
            "building_id": ["B1"],
            "usage_1": ["Résidentiel"],
        },
        geometry=[Polygon([(0, 0), (0, 10), (10, 10), (10, 0)])],
        crs="EPSG:2154",
    )

    config = {"infrastructures": {"schools": {"school_a": {"name": "School A", "capacity": 10}}}}

    result = integrer_ecoles_aux_batiments(gdf, config)

    assert "is_school" not in result.columns
    assert result["usage_1"].tolist() == ["Résidentiel"]
