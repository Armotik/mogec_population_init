import geopandas as gpd
from src.io.loaders import get_study_area_boundary
from src.core.geometry import filter_buildings_by_area, compute_centroids
from src.core.spatial_join import join_buildings_to_grid
from src.core.downscaling import ventiler_population_residentielle
from src.core.cleaning import clip_to_strict_boundary


def test_pipeline_final_with_cleaning(bati_raw, boundary_poly, config):
    # 1. Pipeline complet avec Buffer (6390 bâtiments)
    bati_filtre = filter_buildings_by_area(bati_raw, config['filtering']['min_building_area_m2'])
    bati_prets = compute_centroids(bati_filtre)
    grid_brut = gpd.read_file(config['data_paths']['input']['filosofi'], mask=boundary_poly)
    jointure = join_buildings_to_grid(bati_prets, grid_brut)
    pop_ventilee = ventiler_population_residentielle(jointure, config)

    # 2. Récupération du masque STRICT (0m de buffer)
    strict_boundary = get_study_area_boundary(
        config['study_area']['commune_name'],
        config['project']['crs_epsg'],
        buffer_m=0
    )

    # 3. Nettoyage final
    final_gdf = clip_to_strict_boundary(pop_ventilee, strict_boundary)

    # 4. Bilan final
    print(f"\n" + "=" * 40)
    print(f" BILAN FINAL BATZ-SUR-MER (Xynthia)")
    print(f"=" * 40)
    print(f"Bâtiments finaux : {len(final_gdf)}")
    print(f"Population finale : {final_gdf['pop_t0'].sum()} agents")
    print(f"=" * 40)

    assert len(final_gdf) < len(pop_ventilee)
    assert final_gdf['pop_t0'].sum() < 4545  # Doit être inférieur au résultat avec buffer