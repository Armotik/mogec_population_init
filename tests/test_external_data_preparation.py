from pathlib import Path

import geopandas as gpd
import pandas as pd
from shapely.geometry import LineString, Polygon

from src.io.external_data_preparation import prepare_external_sources


def _write_csv(path: Path, rows: list[dict]) -> None:
    pd.DataFrame(rows).to_csv(path, sep=";", index=False)


def _base_config(tmp_path: Path) -> dict:
    boundary_path = tmp_path / "boundary.gpkg"
    building_path = tmp_path / "buildings.gpkg"
    beaches_path = tmp_path / "beaches.shp"
    capacity_path = tmp_path / "tourism_capacity.csv"

    seed_points = gpd.GeoSeries.from_xy(
        [-2.4900, -2.4880, -2.4860],
        [47.2700, 47.2710, 47.2720],
        crs="EPSG:4326",
    ).to_crs("EPSG:2154")

    boundary = gpd.GeoDataFrame(
        {"libelle_commune": ["Batz-sur-Mer"]},
        geometry=[seed_points.union_all().buffer(500)],
        crs="EPSG:2154",
    )
    boundary.to_file(boundary_path, layer="commune", driver="GPKG")

    buildings = gpd.GeoDataFrame(
        {
            "usage_1": ["Commercial et services", "Commercial et services", "Résidentiel"],
            "nature": ["Bâtiment", "Bâtiment", "Bâtiment"],
        },
        geometry=[point.buffer(30, cap_style=3) for point in seed_points],
        crs="EPSG:2154",
    )
    buildings.to_file(building_path, layer="batiment", driver="GPKG")

    beaches = gpd.GeoDataFrame(
        {"id": [1], "commune": ["batz sur mer"], "nom": ["plage Test"]},
        geometry=[LineString([(seed_points.iloc[0].x - 80, seed_points.iloc[0].y - 120), (seed_points.iloc[0].x + 80, seed_points.iloc[0].y - 120)])],
        crs="EPSG:2154",
    )
    beaches.to_file(beaches_path)

    pd.DataFrame(
        [
            {"GEO": "44010", "GEO_OBJECT": "COM", "ACTIVITY": "I551", "UNIT_LOC_RANKING": "_T", "L_STAY": "_T",
             "TOUR_MEASURE": "UNIT_LOC", "FREQ": "A", "OBS_STATUS": "A", "TIME_PERIOD": 2026, "OBS_VALUE": 1},
            {"GEO": "44010", "GEO_OBJECT": "COM", "ACTIVITY": "I551", "UNIT_LOC_RANKING": "_T", "L_STAY": "_T",
             "TOUR_MEASURE": "PLACE", "FREQ": "A", "OBS_STATUS": "A", "TIME_PERIOD": 2026, "OBS_VALUE": 20},
            {"GEO": "44010", "GEO_OBJECT": "COM", "ACTIVITY": "I553", "UNIT_LOC_RANKING": "_T", "L_STAY": "_T",
             "TOUR_MEASURE": "PLACE", "FREQ": "A", "OBS_STATUS": "A", "TIME_PERIOD": 2026, "OBS_VALUE": 5},
        ]
    ).to_csv(capacity_path, sep=";", index=False)

    return {
        "project": {
            "crs_epsg": 2154,
            "building_id": {"prefix": "TEST", "source_priority": ["geometry_hash"]},
        },
        "study_area": {
            "commune_name": "Batz-sur-Mer, Loire-Atlantique, France",
            "commune_insee": "44010",
            "boundary_path": str(boundary_path),
            "boundary_layer": "commune",
            "boundary_name_field": "libelle_commune",
            "boundary_name_value": "Batz-sur-Mer",
            "buffer_m": 0,
        },
        "data_paths": {
            "input": {
                "bd_topo": str(building_path),
                "bd_topo_layer": "batiment",
                "tourism_restaurants": str(tmp_path / "restaurants.csv"),
                "tourism_hotels": str(tmp_path / "hotels.csv"),
                "tourism_campings": str(tmp_path / "campings.csv"),
                "tourism_residences": str(tmp_path / "residences.csv"),
                "tourism_collective": str(tmp_path / "collectifs.csv"),
                "tourism_locative": str(tmp_path / "locatifs.csv"),
                "beaches_raw": str(beaches_path),
                "tourism_capacity_insee": str(capacity_path),
            }
        },
        "filtering": {"min_building_area_m2": 9},
        "external_preparation": {
            "output_dir": str(tmp_path / "prepared"),
            "accommodation": {
                "match_max_distance_m": 80,
                "preferred_usage_any_of": ["Commercial et services", "Résidentiel"],
                "capacity_rules": {
                    "hotel_beds_per_room": 2.0,
                    "residence_beds_per_room": 2.0,
                    "camping_persons_per_pitch": 2.5,
                },
            },
            "beaches": {"line_buffer_m": 10.0},
        },
    }


def test_prepare_external_sources_outputs_ready_tables(tmp_path):
    config = _base_config(tmp_path)

    _write_csv(
        Path(config["data_paths"]["input"]["tourism_restaurants"]),
        [
            {
                "Nom de l'offre touristique": "Restaurant Test",
                "Commune": "BATZ-SUR-MER",
                "Code Insee de la Commune": 44010,
                "latitude": 47.2700,
                "longitude": -2.4900,
                "Adresse1": "",
                "Adresse2": "1 rue du test",
                "Adresse3": "",
                "Url du site web": "https://example.org/resto",
                "Horaires d'ouvertures": "01/01/2026||31/12/2026||12:00||22:00",
                "Nombre max couverts": 40,
            },
            {
                "Nom de l'offre touristique": "Hors commune",
                "Commune": "LE CROISIC",
                "Code Insee de la Commune": 44049,
                "latitude": 47.2800,
                "longitude": -2.5200,
                "Adresse1": "",
                "Adresse2": "",
                "Adresse3": "",
                "Url du site web": "",
                "Horaires d'ouvertures": "",
                "Nombre max couverts": 20,
            },
        ],
    )

    _write_csv(
        Path(config["data_paths"]["input"]["tourism_hotels"]),
        [
            {
                "Nom de l'offre touristique": "Hotel Test",
                "Nom de la commune": "BATZ-SUR-MER",
                "Code Insee de la Commune": 44010,
                "Latitude": 47.2710,
                "Longitude": -2.4880,
                "Adresse1": "",
                "Adresse partie 1 suite": "",
                "Adresse partie 2": "2 rue hotel",
                "Adresse partie 3": "",
                "Url du site web": "https://example.org/hotel",
                "Horaires d'ouvertures": "",
                "Nombre chambres": 10,
            }
        ],
    )

    _write_csv(
        Path(config["data_paths"]["input"]["tourism_campings"]),
        [
            {
                "Nom de l'offre touristique": "Camping Test",
                "Nom de la commune": "BATZ-SUR-MER",
                "Code Insee de la Commune": 44010,
                "Latitude": 47.2701,
                "Longitude": -2.4901,
                "Adresse1": "",
                "Adresse partie 1 suite": "",
                "Adresse partie 2": "3 rue camping",
                "Adresse partie 3": "",
                "Url du site web": "https://example.org/camping",
                "Période/horaires par jour/précisions ouverture/précision fermeture": "",
                "Nombre emplacements pour les campings": 4,
                "Nombre emplacements équipés avec locatif pour les campings": 2,
                "Nombre emplacements nus pour les campings": 2,
            }
        ],
    )

    _write_csv(
        Path(config["data_paths"]["input"]["tourism_residences"]),
        [
            {
                "Nom de l'offre touristique": "Residence Test",
                "Commune": "BATZ-SUR-MER",
                "Code Insee de la Commune": 44010,
                "Latitude": 47.2720,
                "Longitude": -2.4860,
                "Adresse1": "",
                "Adresse partie 1 suite": "",
                "Adresse partie 2": "4 rue residence",
                "Adresse partie 3": "",
                "Url du site web": "",
                "Horaires d'ouvertures": "",
            }
        ],
    )

    _write_csv(
        Path(config["data_paths"]["input"]["tourism_collective"]),
        [
            {
                "Nom de l'offre touristique": "Centre Test",
                "Nom de la commune": "BATZ-SUR-MER",
                "Code Insee de la Commune": 44010,
                "Latitude": 47.2710,
                "Longitude": -2.4880,
                "Adresse1": "",
                "Adresse partie 1 suite": "",
                "Adresse partie 2": "5 rue collective",
                "Adresse partie 3": "",
                "Url du site web": "",
                "Horaires d'ouvertures": "",
                "Nombre lits": 12,
                "Nombre personnes": 20,
                "Nombre chambres": 6,
            }
        ],
    )

    _write_csv(
        Path(config["data_paths"]["input"]["tourism_locative"]),
        [
            {
                "Nom de l'offre touristique": "Locatif Test",
                "Nom de la commune": "BATZ-SUR-MER",
                "Code Insee de la Commune": 44010,
                "Latitude": 47.2720,
                "Longitude": -2.4860,
                "Adresse1": "",
                "Adresse partie 1 suite": "",
                "Adresse partie 2": "6 rue locative",
                "Adresse partie 3": "",
                "Url du site web": "",
                "Horaires d'ouvertures": "",
                "Nombre personnes": 4,
                "Nombre chambres": 2,
                "Nombre total d'hébergements / logements": 1,
            }
        ],
    )

    outputs = prepare_external_sources(config)

    restaurants = pd.read_csv(outputs["restaurants"], sep=";")
    assert restaurants["nom"].tolist() == ["Restaurant Test"]

    capacity = pd.read_csv(outputs["accommodation_capacity"])
    assert "building_id" in capacity.columns
    assert capacity["capacity_lits"].sum() == 46

    beaches = gpd.read_file(outputs["beaches"], layer="beaches")
    assert len(beaches) == 1
    assert beaches.geometry.iloc[0].geom_type in {"Polygon", "MultiPolygon"}

    tourism = gpd.read_file(outputs["tourism_offers"], layer="tourism_offers")
    assert set(tourism["dataset_type"]) == {"restaurant", "hotel", "camping", "residence", "collective", "locative"}

    summary = pd.read_csv(outputs["accommodation_summary"])
    assert "official_value" in summary.columns

    calibration = pd.read_csv(outputs["accommodation_calibration"])
    assert set(calibration["parameter_name"]) >= {"hotel_beds_per_room", "camping_persons_per_pitch"}

    overlap = pd.read_csv(outputs["accommodation_overlap_audit"])
    assert "overlap_risk" in overlap.columns
    assert "recommended_action" in overlap.columns
