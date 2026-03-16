import geopandas as gpd
from shapely.geometry import Polygon

from src.visualization.validation import (
    hourly_population_profile,
    non_residential_validation,
    occupied_buildings_by_usage,
    role_targets_vs_realized,
    structural_quality_report,
    summarize_export_metrics,
    temporal_variation_buildings,
)


def test_validation_helpers_return_coherent_tables(config):
    gdf = gpd.GeoDataFrame(
        {
            "building_id": ["B1", "B2"],
            "usage_1": ["Residentiel", "Commercial et services"],
            "pop_t0": [4, 2],
            "n_scolaire": [1, 0],
            "n_senior": [1, 0],
            "n_actif_local": [1, 1],
            "n_actif_navetteur": [1, 1],
            "pop_nonres_accommodation": [0, 2],
            "pop_nonres_activity": [0, 1],
            "accommodation_overlap_action": ["excluded_residential_overlap", "added_non_residential_building"],
            "pop_h0": [4, 2],
            "pop_h1": [3, 4],
            "pop_h2": [2, 5],
        },
        geometry=[
            Polygon([(0, 0), (0, 10), (10, 10), (10, 0)]),
            Polygon([(20, 0), (20, 10), (30, 10), (30, 0)]),
        ],
        crs="EPSG:2154",
    )

    quality = structural_quality_report(gdf)
    metrics = summarize_export_metrics(gdf)
    hourly = hourly_population_profile(gdf)
    roles = role_targets_vs_realized(gdf, config)
    nonres = non_residential_validation(gdf)
    variation = temporal_variation_buildings(gdf, top_n=1)
    occupied = occupied_buildings_by_usage(gdf)

    assert int(quality.loc[quality["check"] == "hourly_column_count", "value"].iloc[0]) == 3
    assert "population_t0" in metrics["metric"].tolist()
    assert hourly["population"].tolist() == [6.0, 7.0, 7.0]
    assert set(roles["role"]) == {"scolaire", "senior", "actif_local", "actif_navetteur"}
    assert "Hebergement touristique" in nonres["component"].tolist()
    assert len(variation) == 1
    assert int(occupied["population_t0"].sum()) == 6
