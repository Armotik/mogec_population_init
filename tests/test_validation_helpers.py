import geopandas as gpd
from shapely.geometry import Polygon

from src.visualization.validation import (
    evidence_traceability_report,
    external_proxy_validation,
    hourly_population_profile,
    non_residential_validation,
    occupied_buildings_by_usage,
    plot_scientific_validation_dashboard,
    role_targets_vs_realized,
    scientific_methodology_checklist,
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
            "n_scolaire_interne": [1, 0],
            "n_scolaire_exterieur": [0, 0],
            "n_senior": [1, 0],
            "n_actif_local": [1, 1],
            "n_actif_navetteur": [1, 1],
            "n_inactif": [0, 0],
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
    proxies = external_proxy_validation(gdf, config)
    variation = temporal_variation_buildings(gdf, top_n=1)
    occupied = occupied_buildings_by_usage(gdf)
    evidence = evidence_traceability_report(config)
    checklist = scientific_methodology_checklist(gdf, config)

    assert int(quality.loc[quality["check"] == "hourly_column_count", "value"].iloc[0]) == 3
    assert "population_t0" in metrics["metric"].tolist()
    assert "heure_reference_scenario" in metrics["metric"].tolist()
    assert hourly["population"].tolist() == [6.0, 7.0, 7.0]
    assert set(roles["role"]) == {"scolaire", "senior", "actif_local", "actif_navetteur", "inactif"}
    assert "Hebergement touristique" in nonres["component"].tolist()
    assert "emplois_locaux" in proxies["proxy"].tolist()
    assert "scolaires_affectes_interne" in proxies["proxy"].tolist()
    scolaire_proxy = proxies.loc[proxies["proxy"] == "scolaires_affectes_interne"].iloc[0]
    assert scolaire_proxy["status"] == "info"
    assert len(variation) == 1
    assert int(occupied["population_t0"].sum()) == 6
    assert "accommodation" in evidence["section"].tolist()
    assert "Alignement temporel" in checklist["dimension"].tolist()
    assert "Veracite externe" in checklist["dimension"].tolist()


def test_plot_scientific_validation_dashboard_creates_file(config, tmp_path):
    gdf = gpd.GeoDataFrame(
        {
            "building_id": ["B1", "B2"],
            "usage_1": ["Residentiel", "Commercial et services"],
            "pop_t0": [4, 2],
            "n_scolaire": [1, 0],
            "n_scolaire_interne": [1, 0],
            "n_scolaire_exterieur": [0, 0],
            "n_senior": [1, 0],
            "n_actif_local": [1, 1],
            "n_actif_navetteur": [1, 1],
            "n_inactif": [0, 0],
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

    output = tmp_path / "validation_dashboard.png"
    path = plot_scientific_validation_dashboard(gdf, config, output)

    assert path.exists()
