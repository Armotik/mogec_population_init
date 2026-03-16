"""
Gestion des identifiants stables des bâtiments.

L'objectif est de disposer d'un identifiant persistant entre les exécutions,
réutilisable dans GAMA, dans les exports d'audit et dans les relations entre
bâtiments au sein du pipeline.
"""

import hashlib
import logging

import geopandas as gpd
import pandas as pd

logger = logging.getLogger(__name__)


def _sanitize_identifier(value: str) -> str:
    return "".join(char if char.isalnum() else "_" for char in str(value)).strip("_")


def _geometry_fingerprint(geometry) -> str:
    digest = hashlib.sha1(geometry.wkb).hexdigest()
    return digest[:12]


def assign_building_ids(gdf: gpd.GeoDataFrame, config: dict) -> gpd.GeoDataFrame:
    """
    Assigne un identifiant bâtiment stable et reproductible.

    La stratégie suit l'ordre de priorité défini dans `project.building_id`.
    Les attributs métiers existants sont utilisés en priorité (`cleabs`,
    `identifiants_rnb`). En dernier recours, un hash de géométrie est généré.
    """
    logger.info("Attribution d'identifiants stables aux bâtiments...")

    df = gdf.copy()
    id_config = config['project'].get('building_id', {})
    prefix = id_config.get('prefix', 'BLD')
    source_priority = id_config.get('source_priority', ['cleabs', 'identifiants_rnb', 'geometry_hash'])

    building_ids = []
    building_sources = []

    for _, row in df.iterrows():
        chosen_value = None
        chosen_source = None

        for source in source_priority:
            if source == 'geometry_hash':
                chosen_value = _geometry_fingerprint(row.geometry)
                chosen_source = source
                break

            value = row.get(source)
            if pd.notna(value) and str(value).strip():
                chosen_value = _sanitize_identifier(str(value))
                chosen_source = source
                break

        if chosen_value is None:
            chosen_value = _geometry_fingerprint(row.geometry)
            chosen_source = 'geometry_hash'

        building_ids.append(f"{prefix}_{chosen_value}")
        building_sources.append(chosen_source)

    df['building_id'] = building_ids
    df['building_id_source'] = building_sources

    if not df['building_id'].is_unique:
        duplicate_rank = df.groupby('building_id').cumcount()
        duplicate_mask = duplicate_rank > 0
        df.loc[duplicate_mask, 'building_id'] = (
            df.loc[duplicate_mask, 'building_id'] + "_" + duplicate_rank.loc[duplicate_mask].astype(str)
        )

    logger.info(f"Identifiants stables attribués à {len(df)} bâtiments.")
    return df
