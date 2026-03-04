import pytest
from src.core.geometry import filter_buildings_by_area, compute_centroids
from src.core.spatial_join import join_buildings_to_grid
from src.core.downscaling import ventiler_population_residentielle
from src.core.cleaning import clip_to_strict_boundary
from src.core.profiling import generer_profils_batiments
import geopandas as gpd

from src.io.loaders import get_study_area_boundary


@pytest.fixture(scope="module")
def bati_popule(bati_raw, boundary_poly, config):
    """Prépare un GeoDataFrame propre et peuplé pour le profiling."""
    strict_boundary = get_study_area_boundary(config['study_area']['commune_name'], config['project']['crs_epsg'],
                                              buffer_m=0)

    bati_filtre = filter_buildings_by_area(bati_raw, config['filtering']['min_building_area_m2'])
    bati_prets = compute_centroids(bati_filtre)
    grid_brut = gpd.read_file(config['data_paths']['input']['filosofi'], mask=boundary_poly)
    jointure = join_buildings_to_grid(bati_prets, grid_brut)
    pop_ventilee = ventiler_population_residentielle(jointure, config)
    return clip_to_strict_boundary(pop_ventilee, strict_boundary)


def test_generer_profils_batiments(bati_popule):
    df_profile = generer_profils_batiments(bati_popule)

    # Vérification 1 : Les colonnes existent
    assert 'prob_senior' in df_profile.columns
    assert 'prob_enfant' in df_profile.columns

    # Vérification 2 : Les probabilités sont dans [0, 1]
    assert df_profile['prob_senior'].min() >= 0
    assert df_profile['prob_senior'].max() <= 1

    # Vérification 3 : Cohérence (La somme des âges doit être ~1)
    somme_age = df_profile['prob_enfant'] + df_profile['prob_adulte'] + df_profile['prob_senior']
    assert somme_age.mean() == pytest.approx(1.0, rel=1e-1)

    print(f"\n[Profiling] Probabilité moyenne de seniors à Batz : {df_profile['prob_senior'].mean():.2%}")