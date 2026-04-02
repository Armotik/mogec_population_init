"""
Rattachement des ecoles connues aux emprises bati.

Sur certains territoires, la BD TOPO locale ne qualifie pas explicitement les
ecoles en `usage_1 = Enseignement`. Ce module enrichit alors le bati a partir
de points d'ecoles documentes dans la configuration.
"""

from __future__ import annotations

import logging

import geopandas as gpd
import pandas as pd
from pyproj import Transformer
from shapely.geometry import Point

logger = logging.getLogger(__name__)


def _school_entries(config: dict) -> list[dict]:
    schools = []
    for school_key, school_cfg in config.get("infrastructures", {}).get("schools", {}).items():
        if not isinstance(school_cfg, dict):
            continue
        longitude = school_cfg.get("longitude")
        latitude = school_cfg.get("latitude")
        if longitude is None or latitude is None:
            continue
        schools.append(
            {
                "school_key": str(school_key),
                "name": str(school_cfg.get("name", school_key)),
                "capacity": int(school_cfg.get("capacity", 0)),
                "longitude": float(longitude),
                "latitude": float(latitude),
            }
        )
    return schools


def _usage_priority(value: str, preferred_usages: list[str]) -> int:
    normalized = str(value or "").casefold()
    for index, preferred in enumerate(preferred_usages):
        if normalized == str(preferred).casefold():
            return index
    return len(preferred_usages) + 1


def _best_candidate_for_school(gdf: gpd.GeoDataFrame, school: dict, config: dict, assigned_ids: set[str]) -> tuple[str | None, float | None]:
    matching_cfg = config.get("infrastructures", {}).get("school_matching", {})
    max_distance_m = float(matching_cfg.get("match_max_distance_m", 120.0))
    min_area_m2 = float(matching_cfg.get("min_building_area_m2", 80.0))
    preferred_usages = list(
        matching_cfg.get(
            "preferred_usage_any_of",
            ["Enseignement", "Commercial et services", "Indifférencié", "Résidentiel"],
        )
    )

    transformer = Transformer.from_crs(4326, gdf.crs, always_xy=True)
    x, y = transformer.transform(school["longitude"], school["latitude"])
    school_point = Point(x, y)

    candidates = gdf.copy()
    candidates["school_match_distance_m"] = candidates.geometry.centroid.distance(school_point)
    candidates = candidates[candidates["school_match_distance_m"] <= max_distance_m].copy()
    if candidates.empty:
        return None, None

    candidates["usage_priority"] = candidates["usage_1"].apply(lambda value: _usage_priority(value, preferred_usages))
    candidates["is_unassigned"] = ~candidates["building_id"].astype(str).isin(assigned_ids)
    candidates["meets_area_threshold"] = candidates["surface_sol"].fillna(candidates.geometry.area) >= min_area_m2
    candidates["surface_sol_filled"] = candidates["surface_sol"].fillna(candidates.geometry.area)

    preferred_pool = candidates[candidates["is_unassigned"] & candidates["meets_area_threshold"]]
    if preferred_pool.empty:
        preferred_pool = candidates[candidates["meets_area_threshold"]]
    if preferred_pool.empty:
        preferred_pool = candidates[candidates["is_unassigned"]]
    if preferred_pool.empty:
        preferred_pool = candidates

    preferred_pool = preferred_pool.sort_values(
        by=["usage_priority", "school_match_distance_m", "surface_sol_filled"],
        ascending=[True, True, False],
    )
    selected = preferred_pool.iloc[0]
    return str(selected["building_id"]), float(selected["school_match_distance_m"])


def integrer_ecoles_aux_batiments(gdf: gpd.GeoDataFrame, config: dict) -> gpd.GeoDataFrame:
    """
    Rattache les ecoles configurees aux batiments les plus plausibles.
    """
    schools = _school_entries(config)
    if not schools:
        logger.info("Aucune ecole geolocalisee dans la configuration; aucun enrichissement scolaire applique.")
        return gdf

    logger.info("Rattachement des ecoles configurees aux batiments BD TOPO...")
    df = gdf.copy()
    if "surface_sol" not in df.columns:
        df["surface_sol"] = df.geometry.area

    for column, default in [
        ("is_school", False),
        ("school_name", ""),
        ("school_capacity", 0),
        ("school_count", 0),
        ("school_match_distance_m", pd.NA),
        ("school_match_source", ""),
    ]:
        if column not in df.columns:
            df[column] = default

    if "usage_1_bdtopo" not in df.columns:
        df["usage_1_bdtopo"] = df["usage_1"]

    assigned_ids: set[str] = set()
    matched_count = 0
    for school in schools:
        building_id, distance_m = _best_candidate_for_school(df, school, config, assigned_ids)
        if building_id is None:
            logger.warning("Aucun batiment plausible trouve pour l'ecole '%s'.", school["name"])
            continue

        mask = df["building_id"].astype(str) == building_id
        existing_names = [name for name in str(df.loc[mask, "school_name"].iloc[0]).split(" | ") if name]
        if school["name"] not in existing_names:
            existing_names.append(school["name"])

        df.loc[mask, "is_school"] = True
        df.loc[mask, "school_name"] = " | ".join(existing_names)
        df.loc[mask, "school_capacity"] = df.loc[mask, "school_capacity"].fillna(0).astype(int) + int(school["capacity"])
        df.loc[mask, "school_count"] = df.loc[mask, "school_count"].fillna(0).astype(int) + 1
        df.loc[mask, "school_match_distance_m"] = round(float(distance_m), 2)
        df.loc[mask, "school_match_source"] = "config.school_point_match"
        df.loc[mask, "usage_1"] = "Enseignement"

        assigned_ids.add(building_id)
        matched_count += 1
        logger.info(
            "Ecole '%s' appariee au batiment %s (distance %.2fm).",
            school["name"],
            building_id,
            distance_m,
        )

    logger.info("%s ecole(s) rattachee(s) a %s batiment(s).", matched_count, int(df["is_school"].sum()))
    return df
