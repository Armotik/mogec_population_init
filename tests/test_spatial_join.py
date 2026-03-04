import geopandas as gpd
from src.core.spatial_join import join_buildings_to_grid
from src.core.geometry import filter_buildings_by_area, compute_centroids


def test_join_buildings_to_grid(bati_raw, boundary_poly, config):
    """Vérifie la fusion entre BD TOPO et Filosofi."""
    # Préparation
    bati_filtre = filter_buildings_by_area(bati_raw, config['filtering']['min_building_area_m2'])
    bati_prets = compute_centroids(bati_filtre)

    # Chargement carroyage
    grid_brut = gpd.read_file(config['data_paths']['input']['filosofi'], mask=boundary_poly)

    jointure = join_buildings_to_grid(bati_prets, grid_brut)

    print(f"\n[Spatial Join] {len(jointure)} bâtiments associés aux carreaux INSEE.")
    # Vérifie qu'on a bien récupéré la colonne de population 'ind'
    assert 'ind' in jointure.columns
    assert not jointure.empty