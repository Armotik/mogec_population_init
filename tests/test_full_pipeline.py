import pytest
from src.io.loaders import get_study_area_boundary
from src.core.geometry import filter_buildings_by_area, compute_centroids
from src.core.spatial_join import join_buildings_to_grid
from src.core.downscaling import ventiler_population_residentielle
from src.core.cleaning import clip_to_strict_boundary
from src.core.profiling import generer_profils_batiments
from src.io.exporters import exporter_pour_gama
import geopandas as gpd


def test_full_pipeline_execution(bati_raw, boundary_poly, config):
    # 1. Masque strict pour le clip final
    strict_boundary = get_study_area_boundary(config['study_area']['commune_name'], config['project']['crs_epsg'],
                                              buffer_m=0)

    # 2. Enchaînement des briques
    # A. Géométrie & Préparation
    bati_filtre = filter_buildings_by_area(bati_raw, config['filtering']['min_building_area_m2'])
    bati_prets = compute_centroids(bati_filtre)

    # B. Jointure & Population
    grid_brut = gpd.read_file(config['data_paths']['input']['filosofi'], mask=boundary_poly)
    jointure = join_buildings_to_grid(bati_prets, grid_brut)
    pop_ventilee = ventiler_population_residentielle(jointure, config)

    # C. Nettoyage & Profiling
    pop_nettoyee = clip_to_strict_boundary(pop_ventilee, strict_boundary)
    pop_profilee = generer_profils_batiments(pop_nettoyee)

    # D. Export final
    path_final = exporter_pour_gama(pop_profilee, config)

    assert path_final.exists()
    print(f"\n[PIPELINE OK] Le fichier est prêt pour GAMA : {path_final}")