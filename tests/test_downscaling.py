import pytest
import geopandas as gpd
from shapely.geometry import Polygon
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


def test_ventilation_conserve_masse_quand_carreau_residentiel_est_exclu_culte(config):
    modulateur = (
        1
        + (config['scenario']['residences']['r_rs'] / config['scenario']['residences']['r_rp'])
        * config['scenario']['residences']['tau_saison']
    ) * config['scenario']['residences']['alpha_domicile']

    jointure = gpd.GeoDataFrame(
        {
            'building_id': ['CULTE_ONLY', 'HOME_POOL'],
            'idcar_200m': ['C1', 'C2'],
            'ind': [12.0, 8.0],
            'usage_1': ['Résidentiel', 'Résidentiel'],
            'nombre_de_logements': [6, 4],
            'surface_sol': [240.0, 200.0],
            'hauteur': [10.0, 9.0],
            'is_culte': [True, False],
            'culte_household_allowed': [False, True],
        },
        geometry=[
            Polygon([(0, 0), (0, 10), (10, 10), (10, 0)]),
            Polygon([(100, 0), (100, 10), (110, 10), (110, 0)]),
        ],
        crs='EPSG:2154',
    )

    result = ventiler_population_residentielle(jointure, config)
    cible_globale = int(round(12.0 * modulateur)) + int(round(8.0 * modulateur))

    culte_row = result.loc[result['building_id'] == 'CULTE_ONLY'].iloc[0]
    home_row = result.loc[result['building_id'] == 'HOME_POOL'].iloc[0]

    assert int(result['pop_t0'].sum()) == cible_globale
    assert int(culte_row['pop_t0']) == 0
    assert int(home_row['pop_t0']) == cible_globale
