from __future__ import annotations

from pathlib import Path

import pytest
import geopandas as gpd
from src.io.loaders import load_geopackage_with_mask, load_study_area_boundary
from src.core.geometry import filter_buildings_by_area, compute_centroids
from src.core.identifiers import assign_building_ids
from src.core.spatial_join import join_buildings_to_grid
from src.core.downscaling import ventiler_population_residentielle
from src.core.cleaning import clip_to_strict_boundary
from src.core.temporal import build_member_timelines
from src.pipeline import load_config, run_pipeline

INTEGRATION_FIXTURES = {
    "config",
    "config_weekday_school_day",
    "boundary_poly",
    "strict_boundary_poly",
    "bati_raw",
    "bati_nettoye",
    "bati_popule",
    "bati_popule_weekday_school_day",
    "member_timelines_weekday_school_day",
}
SLOW_NODEID_PATTERNS = (
    "test_full_pipeline.py",
    "test_reproducibility.py",
    "test_profile_activity.py",
    "test_realtime_explorer.py",
    "test_external_data_preparation.py",
    "test_proxy_validation.py",
    "test_proxy_validation_report.py",
)
REPO_ROOT = Path(__file__).resolve().parents[1]
INTEGRATION_DATA_SENTINELS = (
    "data/01_raw/gpkg/referentiel_administratif.gpkg",
    "data/01_raw/gpkg/bdnb.gpkg",
    "data/01_raw/fr-en-ecoles-effectifs-nb_classes.csv",
)


def _infer_test_bucket(fixturenames: set[str], nodeid: str) -> tuple[bool, bool]:
    is_integration = bool(INTEGRATION_FIXTURES.intersection(fixturenames))
    is_slow = is_integration and any(pattern in nodeid for pattern in SLOW_NODEID_PATTERNS)
    return is_integration, is_slow


def _integration_data_available() -> bool:
    return all((REPO_ROOT / sentinel).exists() for sentinel in INTEGRATION_DATA_SENTINELS)


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    data_available = _integration_data_available()
    for item in items:
        fixturenames = set(getattr(item, "fixturenames", ()))
        is_integration, is_slow = _infer_test_bucket(fixturenames, item.nodeid)
        if is_integration:
            item.add_marker(pytest.mark.integration)
            if is_slow:
                item.add_marker(pytest.mark.slow)
            if not data_available:
                item.add_marker(
                    pytest.mark.skip(reason="integration data unavailable in this environment")
                )
        else:
            item.add_marker(pytest.mark.unit)


@pytest.fixture(scope="session")
def config():
    return load_config("config.yaml")


@pytest.fixture(scope="session")
def boundary_poly(config):
    return load_study_area_boundary(config, strict=False)


@pytest.fixture(scope="session")
def strict_boundary_poly(config):
    return load_study_area_boundary(config, strict=True)


@pytest.fixture(scope="session")
def bati_raw(config, boundary_poly):
    return load_geopackage_with_mask(
        config['data_paths']['input']['bd_topo'],
        config['data_paths']['input']['bd_topo_layer'],
        boundary_poly
    )


@pytest.fixture(scope="session")
def bati_nettoye(bati_raw, boundary_poly, strict_boundary_poly, config):
    """Prépare les bâtiments jusqu'au stade post-ventilation et post-clip."""
    # 1. Préparation
    bati_filtre = filter_buildings_by_area(bati_raw, config['filtering']['min_building_area_m2'])
    bati_filtre = assign_building_ids(bati_filtre, config)
    bati_prets = compute_centroids(bati_filtre)

    # 2. Population
    grid_brut = gpd.read_file(config['data_paths']['input']['filosofi'], mask=boundary_poly)
    jointure = join_buildings_to_grid(bati_prets, grid_brut)
    pop_ventilee = ventiler_population_residentielle(jointure, config)
    return clip_to_strict_boundary(pop_ventilee, strict_boundary_poly)


@pytest.fixture(scope="session")
def bati_popule(config):
    """Exécute le pipeline réel pour disposer du jeu final complet."""
    return run_pipeline(config)


@pytest.fixture(scope="session")
def config_weekday_school_day():
    return load_config("config_weekday_school_day.yaml")


@pytest.fixture(scope="session")
def bati_popule_weekday_school_day(config_weekday_school_day):
    return run_pipeline(config_weekday_school_day)


@pytest.fixture(scope="session")
def member_timelines_weekday_school_day(bati_popule_weekday_school_day, config_weekday_school_day):
    return build_member_timelines(bati_popule_weekday_school_day, config_weekday_school_day)
