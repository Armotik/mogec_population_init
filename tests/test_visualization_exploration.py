import geopandas as gpd
from shapely.geometry import Polygon

from src.visualization.exploration import (
    build_destination_assignments,
    destination_type_counts,
    hourly_population_curve,
    role_destination_heatmap,
    summarize_population_metrics,
    top_destination_buildings,
)


def test_exploration_helpers_return_structured_outputs():
    gdf = gpd.GeoDataFrame(
        {
            "building_id": ["B1", "B2", "B3"],
            "usage_1": ["Residentiel", "Enseignement", "Commercial et services"],
            "pop_t0": [2, 0, 0],
            "pop_h0": [2, 0, 0],
            "pop_h1": [1, 1, 0],
            "households": [
                [
                    {
                        "household_id": "B1_hh1",
                        "members": [
                            {"member_id": "m1", "role": "scolaire", "destination_id": "B2"},
                            {"member_id": "m2", "role": "actif_local", "destination_id": "B3"},
                        ],
                    }
                ],
                [],
                [],
            ],
        },
        geometry=[
            Polygon([(0, 0), (0, 10), (10, 10), (10, 0)]),
            Polygon([(20, 0), (20, 10), (30, 10), (30, 0)]),
            Polygon([(0, 20), (0, 30), (10, 30), (10, 20)]),
        ],
        crs="EPSG:2154",
    )

    assignments = build_destination_assignments(gdf)
    metrics = summarize_population_metrics(gdf, assignments)
    hourly = hourly_population_curve(gdf)
    type_counts = destination_type_counts(assignments, top_n=4)
    heatmap = role_destination_heatmap(assignments, top_n=4)
    top_buildings = top_destination_buildings(gdf, assignments, top_n=2)

    assert len(assignments) == 2
    assert set(metrics["metric"]) >= {"population_t0", "flux_internes", "batiments_destination"}
    assert hourly["population"].tolist() == [2, 2]
    assert type_counts["agent_count"].sum() == 2
    assert "scolaire" in heatmap.columns
    assert len(top_buildings) == 2
