import pytest
import yaml
import geopandas as gpd
from src.io.loaders import load_geopackage_with_mask, load_study_area_boundary
from src.core.geometry import filter_buildings_by_area, compute_centroids
from src.core.identifiers import assign_building_ids
from src.core.spatial_join import join_buildings_to_grid
from src.core.downscaling import ventiler_population_residentielle
from src.core.cleaning import clip_to_strict_boundary
from src.pipeline import run_pipeline


@pytest.fixture(scope="session")
def config():
    with open("config.yaml", 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)


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
