"""
Orchestrateur applicatif du pipeline MOGEC.

Ce module assemble les briques de chargement, préparation spatiale,
downscaling résidentiel, enrichissement sociodémographique, intégration des
POI et génération de la matrice horaire. Il constitue la référence du
comportement réel exécuté par `main.py` et par les tests d'intégration.
"""

import logging
from pathlib import Path
from copy import deepcopy

import geopandas as gpd
import yaml

from src.core.agendas import generer_agendas_agents
from src.core.cleaning import clip_to_strict_boundary
from src.core.cultes import integrer_lieux_culte
from src.core.downscaling import ventiler_population_residentielle
from src.core.geometry import compute_centroids, filter_buildings_by_area
from src.core.identifiers import assign_building_ids
from src.core.non_residential import ajouter_zones_plage_exogenes, integrer_population_non_residentielle
from src.core.profiling import generer_profils_batiments
from src.core.restaurants import integrer_restaurants_aux_batiments
from src.core.schools import integrer_ecoles_aux_batiments
from src.core.spatial_join import join_buildings_to_grid
from src.core.temporal import generer_matrice_horaire
from src.io.config_validation import validate_config_for_evidence, validate_config_path_existence
from src.io.exporters import exporter_pour_gama
from src.io.loaders import load_geopackage_with_mask, load_study_area_boundary

logger = logging.getLogger(__name__)


def _deep_merge(base: dict, override: dict) -> dict:
    """
    Fusionne récursivement deux dictionnaires de configuration.

    Le fichier enfant ne duplique ainsi que les paramètres qui changent par
    rapport au scénario de référence.
    """
    merged = deepcopy(base)
    for key, value in override.items():
        if key == "extends":
            continue
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = deepcopy(value)
    return merged


def _looks_like_relative_path(value: str) -> bool:
    if not value or "://" in value:
        return False
    path = Path(value).expanduser()
    return not path.is_absolute() and ("/" in value or "\\" in value)


def normalize_config_paths(config: dict, base_dir: str | Path) -> dict:
    """
    Résout les chemins relatifs d'une configuration par rapport à son YAML source.

    Le YAML contient volontairement des chemins relatifs lisibles dans le dépôt.
    Au runtime, ils doivent toutefois rester valides même si le processus est
    lancé depuis un autre répertoire courant (IDE, service HTTP, tests, etc.).
    """
    base_dir = Path(base_dir).resolve()

    def _normalize(value):
        if isinstance(value, dict):
            return {key: _normalize(item) for key, item in value.items()}
        if isinstance(value, list):
            return [_normalize(item) for item in value]
        if isinstance(value, str) and _looks_like_relative_path(value):
            return str((base_dir / Path(value).expanduser()).resolve())
        return value

    return _normalize(config)


def _load_config_recursive(config_path: Path, inheritance_chain: tuple[Path, ...]) -> dict:
    resolved_config_path = config_path.resolve()
    if resolved_config_path in inheritance_chain:
        cycle = list(inheritance_chain) + [resolved_config_path]
        cycle_str = " -> ".join(str(path) for path in cycle)
        raise ValueError(f"Boucle detectee dans les `extends` YAML: {cycle_str}")

    with open(resolved_config_path, 'r', encoding='utf-8') as file:
        raw_config = yaml.safe_load(file) or {}

    current_config = normalize_config_paths(
        {key: value for key, value in raw_config.items() if key != 'extends'},
        resolved_config_path.parent,
    )

    extends_ref = raw_config.get('extends')
    if extends_ref is None:
        return current_config

    base_path = (resolved_config_path.parent / str(extends_ref)).resolve()
    base_config = _load_config_recursive(base_path, (*inheritance_chain, resolved_config_path))
    return _deep_merge(base_config, current_config)


def load_config(
    config_path: str | Path = "config.yaml",
    require_complete_validation: bool = True,
    require_existing_paths: bool | None = None,
) -> dict:
    """
    Charge le fichier de configuration principal du projet.

    Parameters
    ----------
    config_path:
        Chemin vers le YAML de scénario.
    require_complete_validation:
        Si `True`, impose la présence de toutes les sections top-level attendues.
        Utile en production. Les tests unitaires de chargeur peuvent le désactiver
        pour valider des fragments de YAML synthétiques.
    require_existing_paths:
        Si `True`, vérifie l'existence des chemins configurés (entrées et sorties).
        Par défaut, suit la valeur de `require_complete_validation`.

    Returns
    -------
    dict
        Dictionnaire Python prêt à être consommé par les briques du pipeline.
    """
    config_path = Path(config_path)
    config = _load_config_recursive(config_path, ())
    validate_config_for_evidence(config, require_complete=require_complete_validation)
    if require_existing_paths is None:
        require_existing_paths = require_complete_validation
    if require_existing_paths:
        validate_config_path_existence(config)
    return config


def _load_boundaries(config: dict) -> tuple[gpd.GeoDataFrame, gpd.GeoDataFrame]:
    logger.info("Chargement des frontieres d'etude...")
    boundary = load_study_area_boundary(config, strict=False)
    strict_boundary = load_study_area_boundary(config, strict=True)
    return boundary, strict_boundary


def _load_population_grid(config: dict, boundary: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    logger.info("Chargement du carroyage de population...")
    return gpd.read_file(config['data_paths']['input']['filosofi'], mask=boundary)


def _prepare_buildings(config: dict, boundary: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    logger.info("Preparation du bati avant ventilation residentielle...")
    bati = load_geopackage_with_mask(
        config['data_paths']['input']['bd_topo'],
        config['data_paths']['input']['bd_topo_layer'],
        boundary
    )
    bati = filter_buildings_by_area(bati, config['filtering']['min_building_area_m2'])
    bati = assign_building_ids(bati, config)
    bati = compute_centroids(bati)
    bati = integrer_ecoles_aux_batiments(bati, config)
    return integrer_lieux_culte(bati, config)


def _build_residential_population(
    bati: gpd.GeoDataFrame,
    grid: gpd.GeoDataFrame,
    config: dict,
    strict_boundary: gpd.GeoDataFrame,
) -> gpd.GeoDataFrame:
    logger.info("Ventilation et nettoyage de la population residente...")
    pop = join_buildings_to_grid(bati, grid)
    pop = ventiler_population_residentielle(pop, config)
    pop = integrer_population_non_residentielle(pop, config)
    return clip_to_strict_boundary(pop, strict_boundary)


def _enrich_population_dynamics(pop: gpd.GeoDataFrame, config: dict) -> gpd.GeoDataFrame:
    logger.info("Enrichissement socio-demographique et generation des dynamiques horaires...")
    pop = generer_profils_batiments(pop)
    pop = ajouter_zones_plage_exogenes(pop, config)
    pop = generer_agendas_agents(pop, config)
    pop = integrer_restaurants_aux_batiments(pop, config)
    return generer_matrice_horaire(pop, config)


def run_pipeline(config: dict) -> gpd.GeoDataFrame:
    """
    Exécute l'ensemble du pipeline de génération spatio-temporelle.

    Étapes réalisées
    ----------------
    1. Chargement des frontières d'étude avec et sans buffer.
    2. Lecture du bâti, filtrage géométrique et marquage écoles/culte.
    3. Jointure au carroyage Filosofi et ventilation de `pop_t0`.
    4. Nettoyage strict aux limites communales.
    5. Profilage sociodémographique et génération d'agendas.
    6. Intégration des restaurants.
    7. Construction des colonnes `pop_h0` à `pop_h23`.

    Returns
    -------
    geopandas.GeoDataFrame
        Jeu final enrichi, encore en mémoire, prêt à être exporté.
    """
    boundary, strict_boundary = _load_boundaries(config)
    bati = _prepare_buildings(config, boundary)
    grid = _load_population_grid(config, boundary)
    pop = _build_residential_population(bati, grid, config, strict_boundary)
    return _enrich_population_dynamics(pop, config)


def run_pipeline_to_export(config_path: str | Path = "config.yaml") -> Path:
    """
    Exécute le pipeline complet puis écrit le résultat sur disque.

    Parameters
    ----------
    config_path:
        Chemin vers le YAML de scénario.

    Returns
    -------
    pathlib.Path
        Chemin du GeoPackage final exporté pour GAMA.
    """
    config = load_config(config_path)
    pop = run_pipeline(config)
    return exporter_pour_gama(pop, config)
