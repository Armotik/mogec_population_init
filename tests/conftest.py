import pytest
import yaml
import geopandas as gpd
from src.io.loaders import get_study_area_boundary, load_geopackage_with_mask
from src.core.geometry import filter_buildings_by_area, compute_centroids
from src.core.spatial_join import join_buildings_to_grid
from src.core.downscaling import ventiler_population_residentielle
from src.core.cleaning import clip_to_strict_boundary


@pytest.fixture(scope="session")
def config():
    with open("config.yaml", 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)


@pytest.fixture(scope="session")
def boundary_poly(config):
    return get_study_area_boundary(
        config['study_area']['commune_name'],
        config['project']['crs_epsg'],
        buffer_m=config['study_area'].get('buffer_m', 0)
    )


@pytest.fixture(scope="session")
def bati_raw(config, boundary_poly):
    return load_geopackage_with_mask(
        config['data_paths']['input']['bd_topo'],
        config['data_paths']['input']['bd_topo_layer'],
        boundary_poly
    )


@pytest.fixture(scope="session")
def bati_popule(bati_raw, boundary_poly, config):
    """Génère un GeoDataFrame avec la population ventilée et nettoyée."""
    # 1. Préparation
    strict_boundary = get_study_area_boundary(config['study_area']['commune_name'], config['project']['crs_epsg'],
                                              buffer_m=0)
    bati_filtre = filter_buildings_by_area(bati_raw, config['filtering']['min_building_area_m2'])
    bati_prets = compute_centroids(bati_filtre)

    # 2. Population
    grid_brut = gpd.read_file(config['data_paths']['input']['filosofi'], mask=boundary_poly)
    jointure = join_buildings_to_grid(bati_prets, grid_brut)
    pop_ventilee = ventiler_population_residentielle(jointure, config)

    # 3. Nettoyage final (Clip)
    pop_cleaned = clip_to_strict_boundary(pop_ventilee, strict_boundary)

    # 4. Ajout du profilage et des agendas (nécessaires pour les tests avancés)
    from src.core.profiling import generer_profils_batiments
    from src.core.agendas import generer_agendas_agents
    from src.core.temporal import generer_matrice_horaire

    pop_profiled = generer_profils_batiments(pop_cleaned)
    pop_with_agendas = generer_agendas_agents(pop_profiled, config)
    pop_final = generer_matrice_horaire(pop_with_agendas, config)

    return pop_final
