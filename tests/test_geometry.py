from src.core.geometry import filter_buildings_by_area, compute_centroids


def test_filter_buildings_by_area(bati_raw, config):
    """Vérifie que le filtrage des petits polygones est opérationnel."""
    min_area = config['filtering']['min_building_area_m2']
    initial_count = len(bati_raw)

    gdf_filtered = filter_buildings_by_area(bati_raw, min_area_m2=min_area)

    print(f"\n[Geometry] {initial_count - len(gdf_filtered)} cabanons supprimés sur {initial_count} total.")
    assert len(gdf_filtered) <= initial_count
    assert gdf_filtered['surface_sol'].min() >= min_area


def test_compute_centroids(bati_raw):
    """Vérifie le calcul des points centraux pour la future jointure."""
    gdf_with_centroids = compute_centroids(bati_raw.copy())

    assert 'centroid' in gdf_with_centroids.columns
    assert gdf_with_centroids['centroid'].geom_type.eq('Point').all()