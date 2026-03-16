"""
Sélection probabiliste des destinations.

Le modèle implémente une logique gravitaire paramétrable : un bâtiment de
destination est choisi en fonction de sa capacité, de son attractivité
intrinsèque et de sa distance à l'origine, sous contrainte d'une distance
maximale configurable.
"""

import logging
from typing import Iterable

import geopandas as gpd
import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


def _matches_usage(usage_value: str, patterns: Iterable[str]) -> bool:
    usage_value = str(usage_value or "").casefold()
    return any(pattern.casefold() in usage_value for pattern in patterns)


def _estimate_capacity(row: pd.Series, role_config: dict) -> float:
    capacity_config = role_config.get('capacity', {})
    source_mode = capacity_config.get('source', 'surface_based')

    if source_mode == 'column':
        column_name = capacity_config.get('column')
        value = row.get(column_name)
        if pd.notna(value) and float(value) > 0:
            return float(value)

    if source_mode == 'surface_based':
        sqm_by_usage = capacity_config.get('usage_sqm_per_person', {})
        usage_value = str(row.get('usage_1', ''))
        sqm_per_person = sqm_by_usage.get(usage_value, capacity_config.get('default_sqm_per_person', 30))
        surface = float(row.get('surface_sol', row.geometry.area))
        return max(1.0, surface / max(1.0, float(sqm_per_person)))

    return float(capacity_config.get('default', 1.0))


def _candidate_mask(df: gpd.GeoDataFrame, role_config: dict) -> pd.Series:
    usage_patterns = role_config.get('usage_any_of', [])
    if not usage_patterns:
        return pd.Series(True, index=df.index)
    return df['usage_1'].fillna("").apply(lambda value: _matches_usage(value, usage_patterns))


def sample_destination_building_id(
    origin_row: pd.Series,
    df: gpd.GeoDataFrame,
    role_key: str,
    config: dict,
    rng: np.random.Generator,
) -> str:
    """
    Tire une destination pour un rôle donné à partir d'un modèle gravitaire.
    """
    destination_config = config['destination_model']['role_pools'].get(role_key, {})
    fallback_destination = config['destination_model'].get('fallback_destination', 'EXTERIEUR')

    candidates = df[_candidate_mask(df, destination_config)].copy()
    candidates = candidates[candidates['building_id'] != origin_row['building_id']]

    if candidates.empty:
        return fallback_destination

    distances = candidates.geometry.centroid.distance(origin_row.geometry.centroid)
    max_distance = float(destination_config.get(
        'max_distance_m',
        config['destination_model'].get('default_max_distance_m', 5000)
    ))
    min_distance = float(config['destination_model'].get('min_distance_m', 20))

    candidates = candidates.assign(distance_m=distances)
    candidates = candidates[candidates['distance_m'] <= max_distance]

    if candidates.empty:
        return fallback_destination

    capacity = candidates.apply(lambda row: _estimate_capacity(row, destination_config), axis=1)
    attractiveness_by_usage = destination_config.get('attractiveness_by_usage', {})
    attractiveness = candidates['usage_1'].map(attractiveness_by_usage).fillna(
        float(destination_config.get('attractiveness_weight', 1.0))
    )
    distance_decay = float(destination_config.get(
        'distance_decay',
        config['destination_model'].get('distance_decay', 1.5)
    ))

    impedance = np.maximum(candidates['distance_m'].to_numpy(dtype=float), min_distance) ** distance_decay
    weights = (capacity.to_numpy(dtype=float) * attractiveness.to_numpy(dtype=float)) / impedance
    weights = np.clip(weights, a_min=0.0, a_max=None)

    if float(weights.sum()) <= 0.0:
        return fallback_destination

    probabilities = weights / weights.sum()
    chosen_idx = int(rng.choice(np.arange(len(candidates)), p=probabilities))
    return str(candidates.iloc[chosen_idx]['building_id'])
