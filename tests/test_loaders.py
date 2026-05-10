
import geopandas as gpd
from shapely.geometry import Polygon
import pytest

from src.io.loaders import load_geopackage_with_mask, load_study_area_boundary


def test_get_study_area_boundary(boundary_poly, config):
    """Vérifie que le polygone local de la commune est bien chargé et projeté."""
    target_crs = config['project']['crs_epsg']

    assert not boundary_poly.empty
    assert boundary_poly.crs.to_epsg() == target_crs
    # Vérifie que c'est bien un polygone (ou multipolygone)
    assert boundary_poly.geometry.iloc[0].geom_type in ['Polygon', 'MultiPolygon']


def test_load_bd_topo_with_mask(bati_raw, config):
    """Vérifie que le chargement via le masque (avec buffer) fonctionne."""
    buffer_m = config['study_area'].get('buffer_m', 0)

    assert len(bati_raw) > 0
    print(f"\n[Loader] {len(bati_raw)} bâtiments extraits (Buffer: {buffer_m}m).")


def test_load_study_area_boundary_raises_when_local_file_is_missing_and_fallback_disabled(monkeypatch):
    fallback_boundary = gpd.GeoDataFrame(
        {"name": ["fallback"]},
        geometry=[Polygon([(0, 0), (0, 1), (1, 1), (1, 0)])],
        crs="EPSG:2154",
    )

    called = {}

    def fake_get_study_area_boundary(commune_name, target_crs=2154, buffer_m=0):
        called["args"] = (commune_name, target_crs, buffer_m)
        return fallback_boundary

    monkeypatch.setattr("src.io.loaders.get_study_area_boundary", fake_get_study_area_boundary)

    config = {
        "project": {"crs_epsg": 2154},
        "study_area": {
            "commune_name": "Batz-sur-Mer, Loire-Atlantique, France",
            "boundary_path": "data/01_raw/gpkg/introuvable.gpkg",
            "buffer_m": 200,
            "allow_network_fallback": False,
        },
    }

    with pytest.raises(FileNotFoundError):
        load_study_area_boundary(config, strict=False)
    assert "args" not in called


def test_load_study_area_boundary_raises_when_local_filter_is_empty_and_fallback_disabled(tmp_path, monkeypatch):
    boundary_path = tmp_path / "boundary.gpkg"
    gpd.GeoDataFrame(
        {"libelle_commune": ["Le Croisic"]},
        geometry=[Polygon([(0, 0), (0, 1), (1, 1), (1, 0)])],
        crs="EPSG:4326",
    ).to_file(boundary_path, layer="commune", driver="GPKG")

    fallback_boundary = gpd.GeoDataFrame(
        {"name": ["fallback"]},
        geometry=[Polygon([(0, 0), (0, 2), (2, 2), (2, 0)])],
        crs="EPSG:2154",
    )

    called = {}

    def fake_get_study_area_boundary(commune_name, target_crs=2154, buffer_m=0):
        called["args"] = (commune_name, target_crs, buffer_m)
        return fallback_boundary

    monkeypatch.setattr("src.io.loaders.get_study_area_boundary", fake_get_study_area_boundary)

    config = {
        "project": {"crs_epsg": 2154},
        "study_area": {
            "commune_name": "Batz-sur-Mer, Loire-Atlantique, France",
            "boundary_path": str(boundary_path),
            "boundary_layer": "commune",
            "boundary_name_field": "libelle_commune",
            "boundary_name_value": "Batz-sur-Mer",
            "buffer_m": 0,
            "allow_network_fallback": False,
        },
    }

    with pytest.raises(FileNotFoundError):
        load_study_area_boundary(config, strict=True)
    assert "args" not in called


def test_load_study_area_boundary_falls_back_when_enabled(tmp_path, monkeypatch):
    boundary_path = tmp_path / "boundary.gpkg"
    gpd.GeoDataFrame(
        {"libelle_commune": ["Le Croisic"]},
        geometry=[Polygon([(0, 0), (0, 1), (1, 1), (1, 0)])],
        crs="EPSG:4326",
    ).to_file(boundary_path, layer="commune", driver="GPKG")

    fallback_boundary = gpd.GeoDataFrame(
        {"name": ["fallback"]},
        geometry=[Polygon([(0, 0), (0, 2), (2, 2), (2, 0)])],
        crs="EPSG:2154",
    )
    called = {}

    def fake_get_study_area_boundary(commune_name, target_crs=2154, buffer_m=0):
        called["args"] = (commune_name, target_crs, buffer_m)
        return fallback_boundary

    monkeypatch.setattr("src.io.loaders.get_study_area_boundary", fake_get_study_area_boundary)
    config = {
        "project": {"crs_epsg": 2154},
        "study_area": {
            "commune_name": "Batz-sur-Mer, Loire-Atlantique, France",
            "boundary_path": str(boundary_path),
            "boundary_layer": "commune",
            "boundary_name_field": "libelle_commune",
            "boundary_name_value": "Batz-sur-Mer",
            "buffer_m": 0,
            "allow_network_fallback": True,
        },
    }

    boundary = load_study_area_boundary(config, strict=True)
    assert boundary is fallback_boundary
    assert called["args"] == ("Batz-sur-Mer, Loire-Atlantique, France", 2154, 0)


def test_load_geopackage_with_mask_rejects_empty_mask(tmp_path):
    gpkg_path = tmp_path / "sample.gpkg"
    gpd.GeoDataFrame(
        {"name": ["A"]},
        geometry=[Polygon([(0, 0), (0, 1), (1, 1), (1, 0)])],
        crs="EPSG:2154",
    ).to_file(gpkg_path, layer="sample", driver="GPKG")

    empty_mask = gpd.GeoDataFrame({"name": []}, geometry=[], crs="EPSG:2154")

    with pytest.raises(ValueError):
        load_geopackage_with_mask(str(gpkg_path), "sample", empty_mask)


def test_load_geopackage_with_mask_rejects_mask_without_crs(tmp_path):
    gpkg_path = tmp_path / "sample.gpkg"
    gpd.GeoDataFrame(
        {"name": ["A"]},
        geometry=[Polygon([(0, 0), (0, 1), (1, 1), (1, 0)])],
        crs="EPSG:2154",
    ).to_file(gpkg_path, layer="sample", driver="GPKG")

    mask_without_crs = gpd.GeoDataFrame(
        {"name": ["mask"]},
        geometry=[Polygon([(0, 0), (0, 2), (2, 2), (2, 0)])],
    )

    with pytest.raises(ValueError):
        load_geopackage_with_mask(str(gpkg_path), "sample", mask_without_crs)
