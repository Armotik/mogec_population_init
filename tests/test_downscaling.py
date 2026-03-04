import pytest
import geopandas as gpd
from src.core.spatial_join import join_buildings_to_grid
from src.core.geometry import filter_buildings_by_area, compute_centroids
from src.core.downscaling import ventiler_population_residentielle


@pytest.fixture(scope="module")
def final_join(bati_raw, boundary_poly, config):
    """Prépare la jointure complète pour le test de ventilation."""
    bati_filtre = filter_buildings_by_area(bati_raw, config['filtering']['min_building_area_m2'])
    bati_prets = compute_centroids(bati_filtre)
    grid_brut = gpd.read_file(config['data_paths']['input']['filosofi'], mask=boundary_poly)
    return join_buildings_to_grid(bati_prets, grid_brut)


def test_ventiler_population_residentielle(final_join, config):
    """Vérifie la cohérence du volume d'agents générés."""
    resultat = ventiler_population_residentielle(final_join, config)

    pop_totale = resultat['pop_t0'].sum()
    print(f"\n[Downscaling] Scénario: {config['scenario']['name']}")
    print(f"-> Population finale générée : {pop_totale} agents.")

    assert 'pop_t0' in resultat.columns
    assert pop_totale > 0
    # Vérification anti-erreur : on ne doit pas avoir plus d'habitants que la capacité théorique max
    assert pop_totale < 10000