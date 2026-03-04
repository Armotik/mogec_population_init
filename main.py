import logging
import yaml
import geopandas as gpd

from src.io.loaders import get_study_area_boundary, load_geopackage_with_mask
from src.core.geometry import filter_buildings_by_area, compute_centroids
from src.core.spatial_join import join_buildings_to_grid
from src.core.downscaling import ventiler_population_residentielle
from src.core.cleaning import clip_to_strict_boundary
from src.core.profiling import generer_profils_batiments
from src.core.agendas import generer_agendas_agents
from src.core.temporal import generer_matrice_horaire
from src.io.exporters import exporter_pour_gama

logging.basicConfig(level=logging.INFO, format='%(levelname)s - %(message)s')


def main():
    print("=== DÉMARRAGE DU PIPELINE MOGEC - BATZ-SUR-MER ===")

    # 1. Chargement de la configuration
    with open("config.yaml", 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f)

    # 2. Préparation spatiale
    boundary = get_study_area_boundary(config['study_area']['commune_name'], config['project']['crs_epsg'],
                                       buffer_m=200)
    strict_boundary = get_study_area_boundary(config['study_area']['commune_name'], config['project']['crs_epsg'],
                                              buffer_m=0)

    bati = load_geopackage_with_mask(config['data_paths']['input']['bd_topo'],
                                     config['data_paths']['input']['bd_topo_layer'], boundary)
    bati = filter_buildings_by_area(bati, config['filtering']['min_building_area_m2'])
    bati_centroids = compute_centroids(bati)

    # 3. Jointure et Ventilation (t=0)
    grid = gpd.read_file(config['data_paths']['input']['filosofi'], mask=boundary)
    jointure = join_buildings_to_grid(bati_centroids, grid)
    pop = ventiler_population_residentielle(jointure, config)
    pop = clip_to_strict_boundary(pop, strict_boundary)

    # 4. Profilage et Agendas
    pop = generer_profils_batiments(pop)
    pop = generer_agendas_agents(pop, config)

    # 5. Dynamique Temporelle (t=0 à t=23)
    pop = generer_matrice_horaire(pop, config)

    # 6. Exportation
    fichier_final = exporter_pour_gama(pop, config)

    print(f"=== PIPELINE TERMINÉ. Fichier prêt : {fichier_final} ===")


if __name__ == "__main__":
    main()