"""
Serveur web local pour lire les profils et les trajectoires simulées.
"""

from __future__ import annotations

from collections import defaultdict
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import logging
import math
from numbers import Integral, Real
from pathlib import Path
import threading
from typing import Any
from urllib.parse import parse_qs, urlparse

import geopandas as gpd
import pandas as pd
from pyproj import Transformer

from src.core.proxy_validation import evaluate_temporal_proxies
from src.core.temporal import build_member_timelines
from src.pipeline import load_config, run_pipeline

logger = logging.getLogger(__name__)
PROJECT_ROOT = Path(__file__).resolve().parents[2]

ROLE_COLORS = {
    "scolaire": "#0f766e",
    "senior": "#6d28d9",
    "actif_local": "#c2410c",
    "actif_navetteur": "#1d4ed8",
    "inactif": "#64748b",
}


def _make_json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (str, bool)):
        return value
    if isinstance(value, dict):
        return {str(key): _make_json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_make_json_safe(item) for item in value]
    if isinstance(value, Integral):
        return int(value)
    if isinstance(value, Real):
        return float(value) if math.isfinite(float(value)) else None
    if hasattr(value, "item"):
        try:
            return _make_json_safe(value.item())
        except (TypeError, ValueError):  # pragma: no cover - defensive fallback
            pass
    try:
        if pd.isna(value):
            return None
    except TypeError:  # pragma: no cover - pandas may reject container-like objects
        pass
    return value


def _scenario_id_from_path(path: Path, root_dir: Path = PROJECT_ROOT) -> str:
    try:
        return path.resolve().relative_to(root_dir.resolve()).as_posix()
    except ValueError:
        return path.name


def discover_root_scenarios(root_dir: Path = PROJECT_ROOT, initial_config_path: str | Path | None = None) -> list[dict[str, str]]:
    scenario_paths = sorted(root_dir.glob("config*.yaml"), key=lambda item: (item.name != "config.yaml", item.name))
    if initial_config_path is not None:
        initial_path = Path(initial_config_path).resolve()
        if initial_path not in [path.resolve() for path in scenario_paths]:
            scenario_paths.append(initial_path)

    descriptors: list[dict[str, str]] = []
    seen_ids: set[str] = set()
    for path in scenario_paths:
        scenario_id = _scenario_id_from_path(path, root_dir)
        if scenario_id in seen_ids:
            continue
        try:
            config = load_config(path)
            scenario_name = str(config.get("scenario", {}).get("name", path.stem))
        except Exception as exc:  # pragma: no cover - defensive logging
            logger.warning("Scenario ignore dans l'explorateur (%s): %s", path, exc)
            continue
        seen_ids.add(scenario_id)
        descriptors.append(
            {
                "id": scenario_id,
                "file_name": path.name,
                "scenario_name": scenario_name,
                "label": f"{scenario_name} ({path.name})",
                "config_path": str(path.resolve()),
            }
        )
    return descriptors


def _coerce_reference_curve_values(reference_curve: object) -> list[float]:
    if isinstance(reference_curve, dict):
        return [
            float(reference_curve[str(hour)]) if str(hour) in reference_curve else float(reference_curve[hour])
            for hour in range(24)
        ]
    if isinstance(reference_curve, (list, tuple)):
        return [float(value) for value in reference_curve]
    return []


def _proxy_validation_payload(gdf_model: gpd.GeoDataFrame, config: dict) -> dict[str, Any]:
    summary_df, curves_df = evaluate_temporal_proxies(gdf_model, config)
    proxy_entries = [proxy for proxy in config.get("proxy_validation", {}).get("temporal_proxies", []) if proxy.get("enabled", True)]
    if not proxy_entries:
        return {
            "active_proxy_count": 0,
            "status_counts": {"pass": 0, "warn": 0, "fail": 0, "info": 0},
            "proxies": [],
        }

    summary_lookup = {
        str(row["proxy_id"]): row.to_dict()
        for _, row in summary_df.iterrows()
    }
    curves_lookup = {
        str(proxy_id): group.sort_values("hour").to_dict(orient="records")
        for proxy_id, group in curves_df.groupby("proxy_id", sort=False)
    }

    proxies_payload: list[dict[str, Any]] = []
    status_counts: dict[str, int] = {"pass": 0, "warn": 0, "fail": 0, "info": 0}
    for proxy in proxy_entries:
        proxy_id = str(proxy.get("proxy_id", ""))
        summary = summary_lookup.get(proxy_id, {})
        evidence = proxy.get("evidence", {})
        status = str(summary.get("status", "info"))
        status_counts[status] = status_counts.get(status, 0) + 1
        proxies_payload.append(
            {
                "proxy_id": proxy_id,
                "label": str(proxy.get("label", proxy_id)),
                "metric": str(proxy.get("metric", "")),
                "role": str(proxy.get("role", "")),
                "state": str(proxy.get("state", "")),
                "usage_any_of": [str(item) for item in proxy.get("usage_any_of", [])],
                "comparison_normalization": str(proxy.get("comparison_normalization", "max")),
                "applicable": bool(summary.get("applicable", True)),
                "status": status,
                "reason": str(summary.get("reason", "evaluated")),
                "correlation": summary.get("correlation"),
                "rmse": summary.get("rmse"),
                "mae": summary.get("mae"),
                "modeled_peak_hour": summary.get("modeled_peak_hour"),
                "reference_peak_hour": summary.get("reference_peak_hour"),
                "peak_hour_gap": summary.get("peak_hour_gap"),
                "formula": str(evidence.get("formula", "")),
                "source_name": str(evidence.get("source_name", summary.get("source_name", ""))),
                "source_url": str(evidence.get("source_url", "")),
                "source_url_secondary": str(evidence.get("source_url_secondary", "")),
                "source_file": str(evidence.get("source_file", "")),
                "confidence": str(evidence.get("confidence", summary.get("confidence", ""))),
                "extraction_date": str(evidence.get("extraction_date", summary.get("extraction_date", ""))),
                "temporal_scope": str(evidence.get("temporal_scope", "")),
                "spatial_scope": str(evidence.get("spatial_scope", "")),
                "extraction_method": str(evidence.get("extraction_method", "")),
                "processing_note": str(evidence.get("processing_note", "")),
                "uncertainty_note": str(evidence.get("uncertainty_note", "")),
                "reference_curve": _coerce_reference_curve_values(proxy.get("reference_curve", [])),
                "curve_rows": curves_lookup.get(proxy_id, []),
            }
        )

    return {
        "active_proxy_count": len(proxies_payload),
        "status_counts": status_counts,
        "proxies": proxies_payload,
    }


def _comparison_set_descriptors(
    config: dict[str, Any],
    config_path: Path,
    scenario_catalog: list[dict[str, str]],
    root_dir: Path = PROJECT_ROOT,
) -> list[dict[str, Any]]:
    catalog_by_id = {item["id"]: item for item in scenario_catalog}
    root_set_entries = [
        {
            "scenario_id": item["id"],
            "label": item["scenario_name"],
            "file_name": item["file_name"],
            "config_path": str(Path(item["config_path"]).resolve()),
        }
        for item in scenario_catalog
    ]
    sets: list[dict[str, Any]] = [
        {
            "id": "root_catalog",
            "label": "Configs racine",
            "entries": root_set_entries,
        }
    ]

    scenario_sets = config.get("proxy_validation", {}).get("scenario_sets", {})
    for set_name, raw_entries in scenario_sets.items():
        entries: list[dict[str, str]] = []
        for raw_entry in raw_entries:
            if isinstance(raw_entry, str):
                candidate_path = (config_path.parent / raw_entry).resolve()
                scenario_id = _scenario_id_from_path(candidate_path, root_dir)
                catalog_entry = catalog_by_id.get(scenario_id)
                entries.append(
                    {
                        "scenario_id": scenario_id,
                        "label": catalog_entry["scenario_name"] if catalog_entry else candidate_path.stem,
                        "file_name": catalog_entry["file_name"] if catalog_entry else candidate_path.name,
                        "config_path": str(candidate_path),
                    }
                )
            elif isinstance(raw_entry, dict) and raw_entry.get("config_path"):
                candidate_path = (config_path.parent / str(raw_entry["config_path"])).resolve()
                scenario_id = _scenario_id_from_path(candidate_path, root_dir)
                catalog_entry = catalog_by_id.get(scenario_id)
                entries.append(
                    {
                        "scenario_id": scenario_id,
                        "label": str(raw_entry.get("label") or (catalog_entry["scenario_name"] if catalog_entry else candidate_path.stem)),
                        "file_name": catalog_entry["file_name"] if catalog_entry else candidate_path.name,
                        "config_path": str(candidate_path),
                    }
                )
        if entries:
            sets.append(
                {
                    "id": set_name,
                    "label": f"Jeu {set_name}",
                    "entries": entries,
                }
            )
    return sets


def _to_latlon(point_xy: list[float] | tuple[float, float] | None, transformer: Transformer) -> list[float] | None:
    if point_xy is None:
        return None
    x, y = point_xy
    lon, lat = transformer.transform(float(x), float(y))
    return [float(lat), float(lon)]


def _destination_descriptor(destination_id: str, building_lookup: pd.DataFrame) -> tuple[str, str]:
    if destination_id == "DOMICILE":
        return "Domicile", "Residentiel"
    if destination_id in {"EXTERIEUR", "None", None}:
        return "Exterieur commune", "Hors commune"
    if destination_id in building_lookup.index:
        row = building_lookup.loc[destination_id]
        usage = str(row.get("usage_1", ""))
        suffix = str(destination_id)[-6:]
        return f"{usage or 'Destination interne'} #{suffix}", usage or "Interne"
    return str(destination_id), "Interne"


def _building_points(gdf_model: gpd.GeoDataFrame, building_lookup: pd.DataFrame) -> dict[str, list[float] | None]:
    transformer = Transformer.from_crs(gdf_model.crs, "EPSG:4326", always_xy=True)
    points: dict[str, list[float] | None] = {}
    for building_id, row in building_lookup.iterrows():
        centroid = row.geometry.centroid
        points[str(building_id)] = _to_latlon([float(centroid.x), float(centroid.y)], transformer)
    return points


def _assigned_destination_point(
    assigned_destination_id: Any,
    building_points: dict[str, list[float] | None],
) -> list[float] | None:
    if assigned_destination_id in {"DOMICILE", "EXTERIEUR", "None", None}:
        return None
    return building_points.get(str(assigned_destination_id))


def _timeline_payload(
    timeline_destinations: list[Any],
    home_point: list[float] | None,
    building_points: dict[str, list[float] | None],
    building_lookup: pd.DataFrame,
) -> tuple[list[str | None], list[str], list[str], list[list[float] | None]]:
    normalized_destinations: list[str | None] = []
    labels: list[str] = []
    usages: list[str] = []
    points: list[list[float] | None] = []

    for destination_id in timeline_destinations:
        label, usage = _destination_descriptor(destination_id, building_lookup)
        normalized_destinations.append(None if destination_id in {"None", None} else str(destination_id))
        labels.append(label)
        usages.append(usage)
        if destination_id == "DOMICILE":
            points.append(home_point)
        elif destination_id in {"EXTERIEUR", "None", None}:
            points.append(None)
        else:
            points.append(building_points.get(str(destination_id)))

    return normalized_destinations, labels, usages, points


def _member_payload(
    row: pd.Series,
    home_point: list[float] | None,
    building_points: dict[str, list[float] | None],
    building_lookup: pd.DataFrame,
) -> dict[str, Any]:
    assigned_destination_id = row["assigned_destination_id"]
    timeline_destinations, timeline_labels, timeline_usages, timeline_points = _timeline_payload(
        row["timeline_destinations"],
        home_point,
        building_points,
        building_lookup,
    )
    return {
        "household_id": str(row.get("household_id") or ""),
        "member_id": str(row["member_id"]),
        "role": str(row["role"]),
        "role_color": ROLE_COLORS.get(str(row["role"]), "#334155"),
        "home_building_id": str(row["home_building_id"]),
        "home_point": home_point,
        "assigned_destination_id": None if assigned_destination_id in {"None", None} else str(assigned_destination_id),
        "assigned_destination_usage": str(row.get("assigned_destination_usage") or ""),
        "assigned_destination_point": _assigned_destination_point(assigned_destination_id, building_points),
        "escort_mode": str(row.get("escort_mode") or "none"),
        "school_access_status": str(row.get("school_access_status") or "not_applicable"),
        "school_distance_m": None if pd.isna(row.get("school_distance_m")) else float(row.get("school_distance_m")),
        "escort_guardian_id": None if pd.isna(row.get("escort_guardian_id")) else row.get("escort_guardian_id"),
        "escort_child_ids": [str(item) for item in row.get("escort_child_ids", [])],
        "escort_stop_hours": [int(hour) for hour in row.get("escort_stop_hours", [])],
        "timeline_states": [str(item) for item in row["timeline_states"]],
        "timeline_destinations": timeline_destinations,
        "timeline_labels": timeline_labels,
        "timeline_usages": timeline_usages,
        "timeline_points": timeline_points,
    }


def _update_household_index(
    households_index: dict[str, dict[str, Any]],
    member_payload: dict[str, Any],
) -> None:
    household_id = member_payload["household_id"] or member_payload["home_building_id"]
    household = households_index.setdefault(
        household_id,
        {
            "household_id": household_id,
            "home_building_id": member_payload["home_building_id"],
            "home_point": member_payload["home_point"],
            "member_ids": [],
            "roles": [],
            "escort_children_count": 0,
        },
    )
    household["member_ids"].append(member_payload["member_id"])
    household["roles"].append(member_payload["role"])
    if member_payload["role"] == "scolaire" and member_payload["escort_mode"] == "escort":
        household["escort_children_count"] += 1


def _households_payload(households_index: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    households_payload: list[dict[str, Any]] = []
    for household in households_index.values():
        role_counts = pd.Series(household["roles"]).value_counts().to_dict()
        households_payload.append(
            {
                "household_id": household["household_id"],
                "home_building_id": household["home_building_id"],
                "home_point": household["home_point"],
                "size": len(household["member_ids"]),
                "member_ids": household["member_ids"],
                "role_counts": {str(key): int(value) for key, value in role_counts.items()},
                "has_children": "scolaire" in household["roles"],
                "escort_children_count": int(household["escort_children_count"]),
            }
        )
    return sorted(households_payload, key=lambda item: item["household_id"])


def _map_bounds(gdf_model: gpd.GeoDataFrame) -> list[list[float]]:
    bounds = gdf_model.to_crs("EPSG:4326").total_bounds
    return [
        [float(bounds[1]), float(bounds[0])],
        [float(bounds[3]), float(bounds[2])],
    ]


def _hourly_place_presence_payload(
    gdf_model: gpd.GeoDataFrame,
    member_timelines: pd.DataFrame,
) -> list[dict[str, int]]:
    usage = gdf_model.get("usage_1", pd.Series("", index=gdf_model.index)).fillna("").astype(str)
    exogenous = gdf_model.get("exogenous_zone_type", pd.Series("", index=gdf_model.index)).fillna("").astype(str)
    cult = gdf_model.get("is_culte", pd.Series(False, index=gdf_model.index)).fillna(False).astype(bool)

    masks = {
        "plage": exogenous.eq("plage"),
        "culte": cult,
        "enseignement": usage.eq("Enseignement"),
        "industrie": usage.eq("Industriel"),
        "travail_services": usage.eq("Commercial et services"),
        "sport_loisir": usage.eq("Sportif"),
    }

    hourly_presence: list[dict[str, int]] = []
    for hour in range(24):
        column = f"pop_h{hour}"
        if column in gdf_model.columns:
            total_by_building = pd.to_numeric(gdf_model[column], errors="coerce").fillna(0.0)
        else:
            total_by_building = pd.Series(0.0, index=gdf_model.index)

        domicile = 0
        exterieur = 0
        for states in member_timelines["timeline_states"]:
            state = str(states[hour])
            if state == "domicile":
                domicile += 1
            elif state == "exterieur":
                exterieur += 1

        hourly_presence.append(
            {
                "hour": hour,
                "domicile": domicile,
                "exterieur": exterieur,
                "plage": int(total_by_building.loc[masks["plage"]].sum()),
                "culte": int(total_by_building.loc[masks["culte"]].sum()),
                "enseignement": int(total_by_building.loc[masks["enseignement"]].sum()),
                "industrie": int(total_by_building.loc[masks["industrie"]].sum()),
                "travail_services": int(total_by_building.loc[masks["travail_services"]].sum()),
                "sport_loisir": int(total_by_building.loc[masks["sport_loisir"]].sum()),
            }
        )

    return hourly_presence


def _map_place_presence_payload(
    gdf_model: gpd.GeoDataFrame,
    building_points: dict[str, list[float] | None],
) -> list[dict[str, Any]]:
    usage = gdf_model.get("usage_1", pd.Series("", index=gdf_model.index)).fillna("").astype(str)
    exogenous = gdf_model.get("exogenous_zone_type", pd.Series("", index=gdf_model.index)).fillna("").astype(str)
    cult = gdf_model.get("is_culte", pd.Series(False, index=gdf_model.index)).fillna(False).astype(bool)
    nature = gdf_model.get("nature", pd.Series("", index=gdf_model.index)).fillna("").astype(str)

    def place_type_for_row(index: int) -> str | None:
        if exogenous.iloc[index] == "plage":
            return "plage"
        if bool(cult.iloc[index]):
            return "culte"
        usage_value = usage.iloc[index]
        if usage_value == "Enseignement":
            return "enseignement"
        if usage_value == "Industriel":
            return "industrie"
        if usage_value == "Commercial et services":
            return "travail_services"
        if usage_value == "Sportif":
            return "sport_loisir"
        return None

    places_payload: list[dict[str, Any]] = []
    for index, row in enumerate(gdf_model.itertuples(index=False)):
        place_type = place_type_for_row(index)
        if place_type is None:
            continue
        building_id = str(getattr(row, "building_id"))
        point = building_points.get(building_id)
        if point is None:
            continue
        hourly_counts = []
        for hour in range(24):
            raw_value = getattr(row, f"pop_h{hour}", 0)
            hourly_counts.append(int(pd.to_numeric(raw_value, errors="coerce")) if not pd.isna(raw_value) else 0)
        if max(hourly_counts) <= 0:
            continue
        places_payload.append(
            {
                "building_id": building_id,
                "type": place_type,
                "label": str(getattr(row, "nom_culte", "") or getattr(row, "nature", "") or getattr(row, "usage_1", "") or building_id),
                "usage": str(getattr(row, "usage_1", "") or ""),
                "nature": str(getattr(row, "nature", "") or ""),
                "point": point,
                "hourly_counts": hourly_counts,
            }
        )
    return places_payload


def _endogenous_presence_by_building(member_timelines: pd.DataFrame) -> dict[str, list[int]]:
    presence: dict[str, list[int]] = defaultdict(lambda: [0] * 24)
    for _, row in member_timelines.iterrows():
        home_building_id = str(row["home_building_id"])
        for hour, destination in enumerate(row["timeline_destinations"]):
            if destination == "DOMICILE":
                presence[home_building_id][hour] += 1
            elif destination not in {"EXTERIEUR", "None", None}:
                presence[str(destination)][hour] += 1
    return dict(presence)


def _map_exogenous_presence_payload(
    gdf_model: gpd.GeoDataFrame,
    member_timelines: pd.DataFrame,
    building_points: dict[str, list[float] | None],
) -> list[dict[str, Any]]:
    endogenous_presence = _endogenous_presence_by_building(member_timelines)
    usage = gdf_model.get("usage_1", pd.Series("", index=gdf_model.index)).fillna("").astype(str)
    exogenous = gdf_model.get("exogenous_zone_type", pd.Series("", index=gdf_model.index)).fillna("").astype(str)
    cult = gdf_model.get("is_culte", pd.Series(False, index=gdf_model.index)).fillna(False).astype(bool)
    nature = gdf_model.get("nature", pd.Series("", index=gdf_model.index)).fillna("").astype(str)
    accommodation = pd.to_numeric(gdf_model.get("pop_nonres_accommodation", pd.Series(0, index=gdf_model.index)), errors="coerce").fillna(0.0)

    def place_type_for_row(index: int) -> str:
        if exogenous.iloc[index] == "plage":
            return "plage"
        if accommodation.iloc[index] > 0:
            return "hebergement"
        if bool(cult.iloc[index]):
            return "culte"
        usage_value = usage.iloc[index]
        if usage_value == "Enseignement":
            return "enseignement"
        if usage_value == "Industriel":
            return "industrie"
        if usage_value == "Commercial et services":
            return "travail_services"
        if usage_value == "Sportif":
            return "sport_loisir"
        return "autre_exogene"

    places_payload: list[dict[str, Any]] = []
    for index, row in enumerate(gdf_model.itertuples(index=False)):
        building_id = str(getattr(row, "building_id"))
        point = building_points.get(building_id)
        if point is None:
            continue
        endogenous_counts = endogenous_presence.get(building_id, [0] * 24)
        hourly_counts: list[int] = []
        for hour in range(24):
            raw_value = getattr(row, f"pop_h{hour}", 0)
            total_value = int(pd.to_numeric(raw_value, errors="coerce")) if not pd.isna(raw_value) else 0
            hourly_counts.append(max(0, total_value - endogenous_counts[hour]))
        if max(hourly_counts) <= 0:
            continue
        places_payload.append(
            {
                "building_id": building_id,
                "type": place_type_for_row(index),
                "label": str(getattr(row, "nom_culte", "") or getattr(row, "nature", "") or getattr(row, "usage_1", "") or building_id),
                "usage": str(getattr(row, "usage_1", "") or ""),
                "nature": str(getattr(row, "nature", "") or ""),
                "point": point,
                "hourly_counts": hourly_counts,
            }
        )
    return places_payload


def build_realtime_explorer_payload(gdf_model: gpd.GeoDataFrame, config: dict) -> dict[str, Any]:
    member_timelines = build_member_timelines(gdf_model, config)
    if member_timelines.empty:
        raise ValueError("Aucune trajectoire individuelle n'a pu etre reconstruite.")

    building_lookup = gdf_model.set_index("building_id")
    building_points = _building_points(gdf_model, building_lookup)

    members_payload: list[dict[str, Any]] = []
    households_index: dict[str, dict[str, Any]] = {}
    school_access_summary: dict[str, int] = defaultdict(int)

    for _, row in member_timelines.iterrows():
        home_building_id = str(row["home_building_id"])
        home_point = building_points.get(home_building_id)
        member_payload = _member_payload(row, home_point, building_points, building_lookup)
        members_payload.append(member_payload)
        _update_household_index(households_index, member_payload)
        school_access_summary[member_payload["school_access_status"]] += 1

    return {
        "scenario_name": config.get("scenario", {}).get("name", "scenario"),
        "reference_hour": int(config.get("scenario", {}).get("reference_hour", 0)),
        "members": members_payload,
        "households": _households_payload(households_index),
        "role_counts": {str(key): int(value) for key, value in member_timelines["role"].value_counts().sort_index().to_dict().items()},
        "school_access_summary": {str(key): int(value) for key, value in sorted(school_access_summary.items())},
        "hourly_place_presence": _hourly_place_presence_payload(gdf_model, member_timelines),
        "map_places": _map_place_presence_payload(gdf_model, building_points),
        "map_exogenous_places": _map_exogenous_presence_payload(gdf_model, member_timelines, building_points),
        "proxy_validation": _proxy_validation_payload(gdf_model, config),
        "map": {
            "bounds": _map_bounds(gdf_model),
        },
    }


def render_realtime_explorer_html() -> str:
    return """<!DOCTYPE html>
<html lang="fr">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Lecture interactive MOGEC</title>
  <style>
    :root {
      --page-bg: #f2ede3;
      --sidebar-bg: #f6f1e8;
      --card: rgba(255, 255, 252, 0.94);
      --card-strong: rgba(248, 244, 235, 0.96);
      --line: #d8d0c0;
      --line-soft: rgba(18, 37, 43, 0.08);
      --ink: #12252b;
      --muted: #5d6a70;
      --accent: #1f4e79;
      --accent-soft: #e7f0f8;
      --shadow: 0 18px 40px rgba(18, 37, 43, 0.08);
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: "IBM Plex Sans", "Segoe UI", sans-serif;
      background:
        radial-gradient(circle at top left, rgba(31, 78, 121, 0.08), transparent 28%),
        radial-gradient(circle at bottom right, rgba(17, 94, 89, 0.08), transparent 26%),
        linear-gradient(180deg, #f7f3e8 0%, var(--page-bg) 100%);
      color: var(--ink);
      overflow: hidden;
    }
    .shell {
      display: grid;
      grid-template-columns: minmax(500px, 560px) 1fr;
      height: 100vh;
    }
    .sidebar {
      padding: 18px;
      border-right: 1px solid var(--line-soft);
      background:
        linear-gradient(180deg, rgba(255,255,255,0.35), transparent 20%),
        var(--sidebar-bg);
      overflow-y: auto;
      min-height: 0;
    }
    .sidebar-shell {
      display: grid;
      gap: 14px;
    }
    .top-strip {
      display: grid;
      gap: 14px;
      position: relative;
    }
    .map-wrap {
      position: relative;
      min-height: 0;
    }
    #map {
      position: relative;
      width: 100%;
      height: 100vh;
      overflow: hidden;
      cursor: grab;
      touch-action: none;
      background:
        radial-gradient(circle at 20% 20%, rgba(255,255,255,0.12), transparent 30%),
        linear-gradient(180deg, #d7e3df 0%, #d0d7dd 100%);
    }
    #map.is-dragging { cursor: grabbing; }
    .map-fallback,
    .map-tiles,
    .map-overlay {
      position: absolute;
      inset: 0;
    }
    .map-fallback {
      background:
        linear-gradient(135deg, rgba(17, 94, 89, 0.24), transparent 30%),
        linear-gradient(180deg, rgba(148, 163, 184, 0.25), rgba(226, 232, 240, 0.10));
    }
    .map-tiles { overflow: hidden; }
    .map-tiles img {
      position: absolute;
      transform-origin: top left;
      pointer-events: none;
      user-select: none;
      -webkit-user-drag: none;
    }
    .map-tiles,
    .map-overlay { pointer-events: none; }
    .map-badge {
      position: absolute;
      left: 16px;
      bottom: 16px;
      z-index: 5;
      background: rgba(255,252,246,0.92);
      border: 1px solid rgba(18,37,43,0.08);
      border-radius: 999px;
      padding: 8px 12px;
      box-shadow: var(--shadow);
      font-size: 0.86rem;
    }
    .card {
      background: var(--card);
      border: 1px solid var(--line-soft);
      border-radius: 24px;
      box-shadow: var(--shadow);
      padding: 18px 20px;
    }
    .hero {
      background:
        radial-gradient(circle at top right, rgba(31, 78, 121, 0.14), transparent 26%),
        linear-gradient(160deg, rgba(255,255,255,0.95) 0%, rgba(248,244,235,0.94) 100%);
    }
    .hero h1 { margin: 0 0 8px; font-size: 2.15rem; line-height: 0.98; letter-spacing: -0.03em; }
    .hero-top {
      display: flex;
      align-items: flex-start;
      justify-content: space-between;
      gap: 14px;
    }
    .hero-tag {
      display: inline-flex;
      align-items: center;
      gap: 8px;
      padding: 7px 12px;
      border-radius: 999px;
      background: rgba(31, 78, 121, 0.10);
      color: var(--accent);
      font-size: 0.78rem;
      font-weight: 700;
      letter-spacing: 0.02em;
      white-space: nowrap;
    }
    .hero-copy {
      display: grid;
      gap: 10px;
      max-width: 38rem;
    }
    .muted, .hero p { color: var(--muted); line-height: 1.5; margin: 0; }
    .hero-note {
      font-size: 0.86rem;
      color: var(--muted);
      padding-top: 6px;
      border-top: 1px solid var(--line-soft);
    }
    .card h3 {
      margin: 0 0 14px;
      font-size: 1.02rem;
      letter-spacing: -0.02em;
    }
    .controls-card {
      background: var(--card-strong);
    }
    .controls-grid {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 12px;
    }
    .field {
      display: grid;
      gap: 6px;
    }
    .field-wide {
      grid-column: 1 / -1;
    }
    .grid-2 { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
    label { display: block; font-size: 0.8rem; color: var(--muted); margin-bottom: 0; font-weight: 600; }
    select, input[type="range"], input[type="number"], button, textarea {
      width: 100%;
      border: 1px solid var(--line);
      border-radius: 14px;
      padding: 11px 13px;
      font: inherit;
      background: rgba(255,255,255,0.92);
      transition: border-color 140ms ease, box-shadow 140ms ease, transform 140ms ease;
    }
    select:focus, input:focus, button:focus, textarea:focus {
      outline: none;
      border-color: rgba(31, 78, 121, 0.45);
      box-shadow: 0 0 0 4px rgba(31, 78, 121, 0.10);
    }
    textarea {
      min-height: 180px;
      resize: vertical;
      font: 0.9rem/1.45 "IBM Plex Mono", "SFMono-Regular", monospace;
      background: #fffdf8;
      contain: layout paint;
    }
    button {
      cursor: pointer;
      background: rgba(255,255,255,0.82);
      font-weight: 600;
    }
    button:hover {
      transform: translateY(-1px);
    }
    button.primary {
      background: linear-gradient(135deg, #2f6996 0%, var(--accent) 100%);
      color: white;
      border-color: transparent;
    }
    .toolbar { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin-top: 12px; }
    .toolbar-single { grid-template-columns: 1fr; }
    .hour-line {
      display: grid;
      grid-template-columns: 1fr auto;
      gap: 12px;
      margin-top: 14px;
      align-items: center;
    }
    .hour-pill {
      min-width: 82px;
      text-align: center;
      border-radius: 999px;
      padding: 8px 12px;
      background: var(--accent-soft);
      font-weight: 700;
      color: var(--accent);
    }
    .stats {
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 10px;
      margin-top: 14px;
    }
    .stat {
      border-radius: 18px;
      background: rgba(255,255,255,0.90);
      border: 1px solid var(--line-soft);
      padding: 13px 14px;
    }
    .stat .label { color: var(--muted); font-size: 0.8rem; }
    .stat .value { font-size: 1.42rem; font-weight: 700; margin-top: 6px; letter-spacing: -0.03em; }
    .stats-breakdown {
      display: grid;
      gap: 10px;
      margin-top: 14px;
    }
    .stats-breakdown-title {
      font-size: 0.82rem;
      font-weight: 700;
      color: var(--muted);
      text-transform: uppercase;
      letter-spacing: 0.06em;
    }
    .stats-breakdown-grid {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 8px;
    }
    .stats-breakdown-item {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      padding: 10px 12px;
      border-radius: 14px;
      background: rgba(255,255,255,0.82);
      border: 1px solid var(--line-soft);
    }
    .stats-breakdown-item strong {
      font-size: 0.9rem;
    }
    .stats-breakdown-item span {
      font-weight: 700;
      color: var(--accent);
    }
    .list { display: grid; gap: 8px; }
    .list-item {
      border-radius: 14px;
      padding: 11px 13px;
      background: rgba(255,255,255,0.82);
      border: 1px solid var(--line-soft);
    }
    .badge {
      display: inline-block;
      border-radius: 999px;
      padding: 2px 8px;
      font-size: 0.74rem;
      background: #e2e8f0;
      margin-right: 6px;
      margin-top: 4px;
    }
    .legend {
      position: absolute;
      right: 16px;
      top: 16px;
      width: min(360px, calc(100% - 32px));
      z-index: 6;
    }
    .swatch {
      width: 11px;
      height: 11px;
      border-radius: 50%;
      display: inline-block;
      margin-right: 8px;
    }
    .config-grid { display: grid; gap: 10px; }
    .checkline { display: flex; align-items: center; gap: 10px; min-height: 42px; }
    .checkline input[type="checkbox"] { width: auto; transform: scale(1.2); }
    .status-row { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 10px; }
    .status-pill {
      display: inline-flex;
      align-items: center;
      border-radius: 999px;
      padding: 5px 10px;
      font-size: 0.78rem;
      font-weight: 700;
      border: 1px solid rgba(18,37,43,0.08);
      background: #fff;
    }
    .status-pass { color: #166534; background: #dcfce7; }
    .status-warn { color: #92400e; background: #fef3c7; }
    .status-fail { color: #991b1b; background: #fee2e2; }
    .status-info { color: #1e3a8a; background: #dbeafe; }
    #proxyChart {
      width: 100%;
      height: 240px;
      margin-top: 10px;
      border: 1px solid rgba(18,37,43,0.08);
      border-radius: 14px;
      background: linear-gradient(180deg, #fffef9 0%, #f3eee3 100%);
    }
    .proxy-meta a { color: var(--accent); text-decoration: none; }
    .proxy-meta a:hover { text-decoration: underline; }
    .proxy-list-item { cursor: pointer; }
    .proxy-list-item.is-active { border-color: #1f4e79; background: #eff6ff; }
    .proxy-list-item:hover { border-color: rgba(31,78,121,0.35); }
    .section-tabs {
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 8px;
      padding: 8px;
      background: rgba(255,255,255,0.60);
      border-radius: 18px;
      border: 1px solid var(--line-soft);
      box-shadow: inset 0 1px 0 rgba(255,255,255,0.65);
      position: sticky;
      top: 0;
      z-index: 8;
      backdrop-filter: blur(8px);
    }
    .section-tab {
      border: 0;
      border-radius: 14px;
      background: transparent;
      color: var(--muted);
      padding: 10px 12px;
      text-align: left;
      display: grid;
      gap: 2px;
    }
    .section-tab strong {
      color: var(--ink);
      font-size: 0.9rem;
    }
    .section-tab span {
      font-size: 0.76rem;
      color: var(--muted);
    }
    .section-tab.is-active {
      background: white;
      color: var(--accent);
      box-shadow: 0 8px 20px rgba(18, 37, 43, 0.06);
    }
    .section-tab.is-active strong,
    .section-tab.is-active span {
      color: inherit;
    }
    .panel-stack {
      display: grid;
      gap: 14px;
      align-content: start;
      min-height: 0;
    }
    .panel-card {
      display: none;
      min-height: 0;
    }
    .panel-card.is-active {
      display: block;
    }
    .panel-header {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      margin-bottom: 14px;
    }
    .panel-header p {
      margin: 0;
      font-size: 0.84rem;
      color: var(--muted);
    }
    .matrix-table {
      width: 100%;
      border-collapse: collapse;
      margin-top: 10px;
      font-size: 0.88rem;
      background: rgba(255,255,255,0.82);
      border-radius: 12px;
      overflow: hidden;
    }
    .matrix-table th,
    .matrix-table td {
      padding: 8px 10px;
      border-bottom: 1px solid rgba(18,37,43,0.08);
      text-align: left;
      vertical-align: top;
    }
    .matrix-table th {
      color: var(--muted);
      font-weight: 600;
      background: rgba(248,250,252,0.9);
    }
    .matrix-table tr.is-current {
      background: #eff6ff;
    }
    @media (max-width: 1080px) {
      body { overflow: auto; }
      .shell {
        grid-template-columns: 1fr;
        height: auto;
      }
      .sidebar {
        min-height: auto;
        overflow: visible;
      }
      .top-strip {
        position: relative;
      }
      .stats {
        grid-template-columns: repeat(2, minmax(0, 1fr));
      }
      .stats-breakdown-grid {
        grid-template-columns: 1fr;
      }
      .controls-grid,
      .grid-2,
      .section-tabs,
      .toolbar {
        grid-template-columns: 1fr;
      }
      .map-wrap, #map {
        min-height: 62vh;
        height: 62vh;
      }
    }
  </style>
</head>
<body>
  <div class="shell">
    <aside class="sidebar">
      <div class="sidebar-shell">
        <div class="top-strip">
          <section class="card hero">
            <div class="hero-top">
              <div class="hero-copy">
                <div class="hero-tag">MOGEC · Lecture scenario</div>
                <h1>Lecture interactive du scenario</h1>
                <p>L'interface est organisee pour lire rapidement un scenario, passer d'un proxy a un foyer ou a une personne, puis revenir a la carte sans perdre le fil.</p>
              </div>
            </div>
            <div class="hero-note">Le fond de secours reste visible si les tuiles externes ne se chargent pas.</div>
          </section>

          <section class="card controls-card">
            <div class="panel-header">
              <div>
                <h3>Pilotage</h3>
                <p>Scenario, filtres, heure lue et actions principales.</p>
              </div>
            </div>
            <div class="controls-grid">
              <div class="field">
                <label for="scenarioSelect">Scenario</label>
                <select id="scenarioSelect"></select>
              </div>
              <div class="field">
                <label for="basemapSelect">Fond de carte</label>
                <select id="basemapSelect">
                  <option value="plan">Plan</option>
                  <option value="satellite">Satellite</option>
                </select>
              </div>
              <div class="field">
                <label for="roleSelect">Profil</label>
                <select id="roleSelect"></select>
              </div>
              <div class="field">
                <label for="householdSelect">Foyer</label>
                <select id="householdSelect"></select>
              </div>
              <div class="field field-wide">
                <label for="memberSelect">Personne</label>
                <select id="memberSelect"></select>
              </div>
            </div>
            <div class="hour-line">
              <input type="range" id="hourSlider" min="0" max="23" step="1" value="0">
              <div class="hour-pill" id="hourLabel">h00</div>
            </div>
            <div class="toolbar">
              <button class="primary" id="playButton">Lecture</button>
              <button id="refreshButton">Recharger le scenario</button>
            </div>
            <div class="toolbar">
              <button id="followMemberButton">Suivi automatique : non</button>
              <button id="resetMapViewButton">Recentrer la carte</button>
            </div>
            <div class="stats" id="statsPanel"></div>
            <div class="stats-breakdown" id="statsBreakdownPanel"></div>
          </section>

          <nav class="section-tabs" aria-label="Navigation laterale">
            <button type="button" class="section-tab is-active" data-panel-target="proxy">
              <strong>Validation</strong>
              <span>proxys et comparaison</span>
            </button>
            <button type="button" class="section-tab" data-panel-target="household">
              <strong>Foyer</strong>
              <span>lecture familiale</span>
            </button>
            <button type="button" class="section-tab" data-panel-target="member">
              <strong>Agent</strong>
              <span>matrice horaire</span>
            </button>
          </nav>
        </div>

        <div class="panel-stack">
          <section class="card panel-card is-active" data-panel="proxy">
            <div class="panel-header">
              <div>
                <h3>Validation par proxy</h3>
                <p>Courbes, statuts, traçabilite et comparaison multi-scenarios.</p>
              </div>
            </div>
            <div class="grid-2">
              <div>
                <label for="proxySelect">Proxy</label>
                <select id="proxySelect"></select>
              </div>
              <div>
                <label for="proxyStatusFilter">Filtre de statut</label>
                <select id="proxyStatusFilter">
                  <option value="all">Tous</option>
                  <option value="pass">PASS</option>
                  <option value="warn">WARN</option>
                  <option value="fail">FAIL</option>
                  <option value="info">INFO</option>
                </select>
              </div>
              <div style="grid-column: 1 / -1;">
                <label>Etat des proxys</label>
                <div class="status-row" id="proxyStatusCounts"></div>
              </div>
            </div>
            <div class="toolbar">
              <button id="exportProxySummaryButton">Exporter synthese CSV</button>
              <button id="exportProxyCurvesButton">Exporter courbes CSV</button>
            </div>
            <div class="list" id="proxyListPanel" style="margin-top: 10px;"></div>
            <div class="list" id="proxySummaryPanel" style="margin-top: 10px;"></div>
            <svg id="proxyChart" viewBox="0 0 620 240" preserveAspectRatio="none"></svg>
            <div class="list proxy-meta" id="proxyMetaPanel" style="margin-top: 10px;"></div>
            <div class="grid-2" style="margin-top: 14px;">
              <div>
                <label for="proxyComparisonSetSelect">Jeu de scenarios</label>
                <select id="proxyComparisonSetSelect"></select>
              </div>
              <div>
                <label>Comparaison multi-scenarios</label>
                <div class="toolbar" style="margin-top: 0;">
                  <button id="loadProxyComparisonButton" class="primary">Lancer comparaison</button>
                  <button id="exportProxyComparisonButton">Exporter comparaison CSV</button>
                </div>
              </div>
            </div>
            <div class="list" id="proxyComparisonPanel" style="margin-top: 10px;"></div>
            <svg id="proxyComparisonChart" viewBox="0 0 620 260" preserveAspectRatio="none" style="width: 100%; height: 260px; margin-top: 10px; border: 1px solid rgba(18,37,43,0.08); border-radius: 14px; background: linear-gradient(180deg, #fffef9 0%, #f3eee3 100%);"></svg>
          </section>

          <section class="card panel-card" data-panel="household">
            <div class="panel-header">
              <div>
                <h3>Foyer courant</h3>
                <p>Composition, accompagnement scolaire et etat courant des membres.</p>
              </div>
            </div>
            <div class="list" id="householdPanel"></div>
          </section>

          <section class="card panel-card" data-panel="member">
            <div class="panel-header">
              <div>
                <h3>Trajectoire individuelle</h3>
                <p>Chronologie, deplacements et matrice horaire de la personne selectionnee.</p>
              </div>
            </div>
            <div class="list" id="memberPanel"></div>
          </section>
        </div>
      </div>
    </aside>

    <main class="map-wrap">
      <div id="map">
        <div class="map-fallback"></div>
        <div class="map-tiles" id="mapTiles"></div>
        <svg class="map-overlay" id="mapOverlay"></svg>
        <div class="map-badge" id="mapBadge">Carte en chargement</div>
      </div>
      <div class="legend card">
        <div class="muted" id="scenarioLabel">Chargement...</div>
        <div id="roleLegend"></div>
      </div>
    </main>
  </div>

  <script>
    const SVG_NS = 'http://www.w3.org/2000/svg';
    const state = {
      data: null,
      hour: 0,
      role: 'all',
      householdId: 'all',
      memberId: 'all',
      activePanel: 'proxy',
      proxyId: '',
      proxyStatusFilter: 'all',
      proxyComparisonSetId: 'root_catalog',
      proxyComparison: null,
      proxyComparisonRequestId: 0,
      proxyComparisonDirty: true,
      playing: false,
      timer: null,
      followSelected: false,
      mapView: { panX: 0, panY: 0, zoomFactor: 1, dragging: false, pointerId: null, lastX: 0, lastY: 0, dragDistance: 0 },
    };

    const scenarioSelect = document.getElementById('scenarioSelect');
    const roleSelect = document.getElementById('roleSelect');
    const householdSelect = document.getElementById('householdSelect');
    const memberSelect = document.getElementById('memberSelect');
    const proxySelect = document.getElementById('proxySelect');
    const proxyStatusFilter = document.getElementById('proxyStatusFilter');
    const proxyComparisonSetSelect = document.getElementById('proxyComparisonSetSelect');
    const basemapSelect = document.getElementById('basemapSelect');
    const hourSlider = document.getElementById('hourSlider');
    const hourLabel = document.getElementById('hourLabel');
    const playButton = document.getElementById('playButton');
    const refreshButton = document.getElementById('refreshButton');
    const followMemberButton = document.getElementById('followMemberButton');
    const resetMapViewButton = document.getElementById('resetMapViewButton');
    const statsPanel = document.getElementById('statsPanel');
    const statsBreakdownPanel = document.getElementById('statsBreakdownPanel');
    const householdPanel = document.getElementById('householdPanel');
    const memberPanel = document.getElementById('memberPanel');
    const roleLegend = document.getElementById('roleLegend');
    const scenarioLabel = document.getElementById('scenarioLabel');
    const proxyStatusCounts = document.getElementById('proxyStatusCounts');
    const proxyListPanel = document.getElementById('proxyListPanel');
    const proxySummaryPanel = document.getElementById('proxySummaryPanel');
    const proxyMetaPanel = document.getElementById('proxyMetaPanel');
    const proxyChart = document.getElementById('proxyChart');
    const proxyComparisonPanel = document.getElementById('proxyComparisonPanel');
    const proxyComparisonChart = document.getElementById('proxyComparisonChart');
    const exportProxySummaryButton = document.getElementById('exportProxySummaryButton');
    const exportProxyCurvesButton = document.getElementById('exportProxyCurvesButton');
    const exportProxyComparisonButton = document.getElementById('exportProxyComparisonButton');
    const loadProxyComparisonButton = document.getElementById('loadProxyComparisonButton');
    const sectionTabs = [...document.querySelectorAll('[data-panel-target]')];
    const panelCards = [...document.querySelectorAll('[data-panel]')];
    const mapRoot = document.getElementById('map');
    const mapTiles = document.getElementById('mapTiles');
    const mapOverlay = document.getElementById('mapOverlay');
    const mapBadge = document.getElementById('mapBadge');

    function switchPanel(panelId) {
      state.activePanel = panelId;
      sectionTabs.forEach((button) => {
        button.classList.toggle('is-active', button.dataset.panelTarget === panelId);
      });
      panelCards.forEach((panel) => {
        panel.classList.toggle('is-active', panel.dataset.panel === panelId);
      });
    }

    function roleName(role) {
      return {
        all: 'Tous profils',
        scolaire: 'Scolaire',
        senior: 'Senior',
        actif_local: 'Actif local',
        actif_navetteur: 'Actif navetteur',
        inactif: 'Inactif',
      }[role] || role;
    }

    function placeTypeName(type) {
      return {
        plage: 'Plage',
        hebergement: 'Hebergement',
        culte: 'Culte',
        enseignement: 'Enseignement',
        industrie: 'Industrie',
        travail_services: 'Commerce / services',
        sport_loisir: 'Sport / loisir',
        autre_exogene: 'Autre exogene',
      }[type] || type;
    }

    function activityName(member, hour) {
      const label = member.timeline_states[hour];
      if (label === 'domicile') return 'Domicile';
      if (label === 'interne') return member.timeline_labels[hour];
      return 'Extérieur de la commune';
    }

    function samePoint(a, b) {
      if (!a || !b) return false;
      return a[0] === b[0] && a[1] === b[1];
    }

    function selectedMember() {
      if (!state.data || state.memberId === 'all') return null;
      return state.data.members.find((member) => member.member_id === state.memberId) || null;
    }

    function filteredMembers() {
      if (!state.data) return [];
      let members = state.data.members;
      if (state.role !== 'all') members = members.filter((member) => member.role === state.role);
      if (state.householdId !== 'all') members = members.filter((member) => member.household_id === state.householdId);
      if (state.memberId !== 'all') members = members.filter((member) => member.member_id === state.memberId);
      return members;
    }

    function householdsForSelection() {
      if (!state.data) return [];
      if (state.role === 'all') return state.data.households;
      const ids = new Set(
        state.data.members
          .filter((member) => member.role === state.role)
          .map((member) => member.household_id)
      );
      return state.data.households.filter((household) => ids.has(household.household_id));
    }

    function populateControls() {
      if (!state.data) return;
      scenarioSelect.innerHTML = state.data.available_scenarios
        .map((scenario) => `<option value="${scenario.id}">${scenario.label}</option>`)
        .join('');
      scenarioSelect.value = state.data.selected_scenario_id;

      roleSelect.innerHTML = ['all', ...Object.keys(state.data.role_counts)]
        .map((role) => `<option value="${role}">${roleName(role)}</option>`)
        .join('');
      roleSelect.value = state.role;

      const households = householdsForSelection();
      householdSelect.innerHTML = ['<option value="all">Tous foyers</option>']
        .concat(households.map((household) => `<option value="${household.household_id}">${household.household_id} (${household.size} pers.)</option>`))
        .join('');
      if (![...householdSelect.options].some((option) => option.value === state.householdId)) state.householdId = 'all';
      householdSelect.value = state.householdId;

      const members = filteredMembers();
      memberSelect.innerHTML = ['<option value="all">Toutes personnes</option>']
        .concat(members.map((member) => `<option value="${member.member_id}">${member.member_id} · ${roleName(member.role)}</option>`))
        .join('');
      if (![...memberSelect.options].some((option) => option.value === state.memberId)) state.memberId = 'all';
      memberSelect.value = state.memberId;

      const proxies = state.data.proxy_validation?.proxies || [];
      proxySelect.innerHTML = proxies.length
        ? proxies.map((proxy) => `<option value="${proxy.proxy_id}">${proxy.label}</option>`).join('')
        : '<option value="">Aucun proxy actif</option>';
      if (!proxies.some((proxy) => proxy.proxy_id === state.proxyId)) {
        state.proxyId = proxies[0]?.proxy_id || '';
      }
      proxySelect.value = state.proxyId;
      proxyStatusFilter.value = state.proxyStatusFilter;

      const comparisonSets = state.data.proxy_comparison_sets || [];
      proxyComparisonSetSelect.innerHTML = comparisonSets.length
        ? comparisonSets.map((item) => `<option value="${item.id}">${item.label} (${item.entries.length})</option>`).join('')
        : '<option value="root_catalog">Configs racine</option>';
      if (!comparisonSets.some((item) => item.id === state.proxyComparisonSetId)) {
        state.proxyComparisonSetId = comparisonSets[0]?.id || 'root_catalog';
      }
      proxyComparisonSetSelect.value = state.proxyComparisonSetId;

      scenarioLabel.textContent = `${state.data.scenario_name} · ${state.data.selected_scenario_file} · T0 = h${String(state.data.reference_hour).padStart(2, '0')}`;
      roleLegend.innerHTML = Object.keys(state.data.role_counts).map((role) => `
        <div style="margin-top: 8px;">
          <span class="swatch" style="background:${state.data.members.find((member) => member.role === role)?.role_color || '#334155'}"></span>
          ${roleName(role)} (${state.data.role_counts[role]})
        </div>
      `).join('');
      followMemberButton.textContent = `Suivi automatique : ${state.followSelected ? 'oui' : 'non'}`;
    }

    function renderStats() {
      const members = filteredMembers();
      const counts = { domicile: 0, interne: 0, exterieur: 0 };
      let escorted = 0;
      let walking = 0;
      members.forEach((member) => {
        counts[member.timeline_states[state.hour]] += 1;
        if (member.role === 'scolaire' && member.escort_mode === 'escort') escorted += 1;
        if (member.role === 'scolaire' && member.escort_mode === 'walk') walking += 1;
      });
      const stats = [
        ['Population affichee', members.length],
        ['Au domicile', counts.domicile],
        ['Dans la commune', counts.interne],
        ['Hors commune', counts.exterieur],
        ['Scolaires a pied', walking],
        ['Scolaires accompagnes', escorted],
      ];
      statsPanel.innerHTML = stats.map(([label, value]) => `
        <div class="stat">
          <div class="label">${label}</div>
          <div class="value">${value}</div>
        </div>
      `).join('');

      const locationLabels = {
        domicile: 'Domicile',
        exterieur: 'Hors commune',
        plage: 'Plage',
        culte: 'Culte',
        enseignement: 'Enseignement',
        industrie: 'Industrie',
        travail_services: 'Commerce / services',
        sport_loisir: 'Sport / loisir',
      };
      const hourlyPresence = state.data?.hourly_place_presence?.[state.hour] || null;
      const breakdownEntries = hourlyPresence
        ? Object.entries(hourlyPresence)
            .filter(([key, value]) => key !== 'hour' && Number(value) > 0)
            .map(([key, value]) => [key, Number(value)])
        : [];
      statsBreakdownPanel.innerHTML = breakdownEntries.length
        ? `
          <div class="stats-breakdown-title">Occupation totale par type de lieu a h${String(state.hour).padStart(2, '0')}</div>
          <div class="stats-breakdown-grid">
            ${breakdownEntries.map(([key, value]) => `
              <div class="stats-breakdown-item">
                <strong>${locationLabels[key] || key}</strong>
                <span>${value}</span>
              </div>
            `).join('')}
          </div>
        `
        : '<div class="muted">Aucune personne visible pour cette selection.</div>';
    }

    function selectedProxy() {
      const proxies = state.data?.proxy_validation?.proxies || [];
      return proxies.find((proxy) => proxy.proxy_id === state.proxyId) || null;
    }

    function filteredProxies() {
      const proxies = state.data?.proxy_validation?.proxies || [];
      if (state.proxyStatusFilter === 'all') return proxies;
      return proxies.filter((proxy) => proxy.status === state.proxyStatusFilter);
    }

    function csvEscape(value) {
      const stringValue = value === null || value === undefined ? '' : String(value);
      if (/[",\\n]/.test(stringValue)) return `"${stringValue.replace(/"/g, '""')}"`;
      return stringValue;
    }

    function downloadCsv(filename, rows) {
      if (!rows.length) return;
      const headers = Object.keys(rows[0]);
      const lines = [
        headers.map(csvEscape).join(','),
        ...rows.map((row) => headers.map((header) => csvEscape(row[header])).join(',')),
      ];
      const blob = new Blob([lines.join('\\n')], { type: 'text/csv;charset=utf-8' });
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = filename;
      document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(url);
    }

    async function fetchJsonOrThrow(url, options = {}) {
      const response = await fetch(url, options);
      const rawText = await response.text();
      let payload;
      try {
        payload = rawText ? JSON.parse(rawText) : {};
      } catch (error) {
        throw new Error(`Reponse JSON invalide depuis ${url} (${error.message})`);
      }
      if (!response.ok) {
        const message = payload?.error || payload?.message || `Requete en echec (${response.status})`;
        throw new Error(message);
      }
      return payload;
    }

    function setLoadingState(message) {
      scenarioLabel.textContent = message;
      mapBadge.textContent = message;
    }

    function reportActionError(error, fallbackMessage) {
      console.error(error);
      const message = error?.message || fallbackMessage;
      scenarioLabel.textContent = message;
      mapBadge.textContent = message;
    }

    function markProxyComparisonDirty(message = 'Comparaison non lancee pour cette selection.') {
      state.proxyComparisonRequestId += 1;
      state.proxyComparisonDirty = true;
      state.proxyComparison = null;
      exportProxyComparisonButton.disabled = true;
      proxyComparisonChart.innerHTML = '';
      proxyComparisonPanel.innerHTML = `<div class="list-item muted">${message}</div>`;
    }

    function proxySummaryRows() {
      return (state.data?.proxy_validation?.proxies || []).map((proxy) => ({
        scenario_name: state.data.scenario_name,
        proxy_id: proxy.proxy_id,
        label: proxy.label,
        metric: proxy.metric,
        applicable: proxy.applicable,
        status: proxy.status,
        reason: proxy.reason,
        comparison_normalization: proxy.comparison_normalization,
        correlation: proxy.correlation,
        rmse: proxy.rmse,
        mae: proxy.mae,
        modeled_peak_hour: proxy.modeled_peak_hour,
        reference_peak_hour: proxy.reference_peak_hour,
        peak_hour_gap: proxy.peak_hour_gap,
        source_name: proxy.source_name,
        extraction_date: proxy.extraction_date,
        confidence: proxy.confidence,
      }));
    }

    function proxyCurveRows() {
      return (state.data?.proxy_validation?.proxies || []).flatMap((proxy) =>
        (proxy.curve_rows || []).map((row) => ({
          scenario_name: state.data.scenario_name,
          proxy_id: proxy.proxy_id,
          label: proxy.label,
          metric: proxy.metric,
          hour: row.hour,
          modeled_value: row.modeled_value,
          reference_value: row.reference_value,
          modeled_compared: row.modeled_compared,
          reference_compared: row.reference_compared,
        }))
      );
    }

    function proxyComparisonRows() {
      return (state.proxyComparison?.scenarios || []).map((row) => ({
        comparison_set: state.proxyComparison?.set_id || '',
        comparison_label: state.proxyComparison?.set_label || '',
        proxy_id: state.proxyComparison?.proxy_id || '',
        proxy_label: state.proxyComparison?.proxy_label || '',
        scenario_name: row.scenario_name,
        scenario_file: row.scenario_file,
        status: row.status,
        applicable: row.applicable,
        reason: row.reason,
        correlation: row.correlation,
        rmse: row.rmse,
        mae: row.mae,
        peak_hour_gap: row.peak_hour_gap,
        source_name: row.source_name,
        extraction_date: row.extraction_date,
        confidence: row.confidence,
      }));
    }

    async function loadProxyComparison() {
      if (!state.proxyId) {
        markProxyComparisonDirty('Aucun proxy selectionne pour la comparaison.');
        return;
      }
      const requestId = ++state.proxyComparisonRequestId;
      state.proxyComparisonDirty = false;
      loadProxyComparisonButton.disabled = true;
      proxyComparisonPanel.innerHTML = '<div class="list-item muted">Chargement de la comparaison multi-scenarios...</div>';
      try {
        const comparison = await fetchJsonOrThrow('/api/proxy-compare', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            proxy_id: state.proxyId,
            scenario_set_id: state.proxyComparisonSetId,
          }),
        });
        if (requestId !== state.proxyComparisonRequestId) return;
        state.proxyComparison = comparison;
        renderProxyComparison();
      } catch (error) {
        if (requestId !== state.proxyComparisonRequestId) return;
        state.proxyComparison = null;
        state.proxyComparisonDirty = true;
        proxyComparisonPanel.innerHTML = `<div class="list-item muted">${error?.message || 'Comparaison indisponible.'}</div>`;
        proxyComparisonChart.innerHTML = '';
        console.error(error);
      } finally {
        if (requestId === state.proxyComparisonRequestId) {
          loadProxyComparisonButton.disabled = false;
        }
      }
    }

    function renderProxyValidation() {
      const proxyValidation = state.data?.proxy_validation;
      const proxies = proxyValidation?.proxies || [];
      const counts = proxyValidation?.status_counts || { pass: 0, warn: 0, fail: 0, info: 0 };
      const visibleProxies = filteredProxies();

      proxyStatusCounts.innerHTML = ['pass', 'warn', 'fail', 'info']
        .map((status) => `<span class="status-pill status-${status}">${status.toUpperCase()} ${counts[status] || 0}</span>`)
        .join('');
      exportProxySummaryButton.disabled = proxies.length === 0;
      exportProxyCurvesButton.disabled = proxies.length === 0;

      if (!proxies.length) {
        proxyListPanel.innerHTML = '';
        proxySummaryPanel.innerHTML = '<div class="list-item muted">Aucun proxy actif dans ce scenario.</div>';
        proxyMetaPanel.innerHTML = '';
        proxyChart.innerHTML = '';
        return;
      }

      if (!visibleProxies.some((proxy) => proxy.proxy_id === state.proxyId)) {
        state.proxyId = visibleProxies[0]?.proxy_id || proxies[0]?.proxy_id || '';
      }
      proxySelect.innerHTML = visibleProxies.length
        ? visibleProxies.map((proxy) => `<option value="${proxy.proxy_id}">${proxy.label}</option>`).join('')
        : '<option value="">Aucun proxy pour ce filtre</option>';
      proxySelect.value = visibleProxies.some((proxy) => proxy.proxy_id === state.proxyId) ? state.proxyId : '';

      proxyListPanel.innerHTML = visibleProxies.length
        ? visibleProxies.map((proxy) => `
            <div class="list-item proxy-list-item ${proxy.proxy_id === state.proxyId ? 'is-active' : ''}" data-proxy-id="${proxy.proxy_id}">
              <strong>${proxy.label}</strong><br>
              <span class="status-pill status-${proxy.status}">${String(proxy.status).toUpperCase()}</span>
              <span class="badge">${proxy.metric}</span>
              ${proxy.applicable ? '' : `<span class="badge">${proxy.reason}</span>`}
            </div>
          `).join('')
        : '<div class="list-item muted">Aucun proxy ne correspond au filtre choisi.</div>';

      const proxy = selectedProxy();
      if (!proxy) {
        proxySummaryPanel.innerHTML = '<div class="list-item muted">Aucun proxy selectionne.</div>';
        proxyMetaPanel.innerHTML = '';
        proxyChart.innerHTML = '';
        return;
      }

      proxySummaryPanel.innerHTML = `
        <div class="list-item">
          <strong>${proxy.label}</strong><br>
          <span class="status-pill status-${proxy.status}">${String(proxy.status).toUpperCase()}</span>
          <span class="badge">${proxy.metric}</span>
          <span class="badge">normalisation : ${proxy.comparison_normalization}</span>
          ${proxy.applicable ? '' : `<span class="badge">motif : ${proxy.reason}</span>`}
        </div>
        <div class="list-item">
          <span class="badge">corr = ${proxy.correlation ?? 'n/a'}</span>
          <span class="badge">rmse = ${proxy.rmse ?? 'n/a'}</span>
          <span class="badge">mae = ${proxy.mae ?? 'n/a'}</span>
          <span class="badge">ecart pic = ${proxy.peak_hour_gap ?? 'n/a'} h</span>
        </div>
      `;

      renderProxyChart(proxy);
      proxyMetaPanel.innerHTML = `
        ${proxy.formula ? `<div class="list-item"><strong>Formule</strong><br>${proxy.formula}</div>` : ''}
        <div class="list-item"><strong>Source</strong><br>${proxy.source_name || 'n/a'}</div>
        <div class="list-item"><strong>Traçabilite</strong><br>
          <span class="badge">confiance : ${proxy.confidence || 'n/a'}</span>
          <span class="badge">date : ${proxy.extraction_date || 'n/a'}</span>
          ${proxy.temporal_scope ? `<span class="badge">temps : ${proxy.temporal_scope}</span>` : ''}
          ${proxy.spatial_scope ? `<span class="badge">espace : ${proxy.spatial_scope}</span>` : ''}
        </div>
        ${proxy.source_url ? `<div class="list-item"><strong>Source web</strong><br><a href="${proxy.source_url}" target="_blank" rel="noreferrer">${proxy.source_url}</a></div>` : ''}
        ${proxy.source_url_secondary ? `<div class="list-item"><strong>Source web secondaire</strong><br><a href="${proxy.source_url_secondary}" target="_blank" rel="noreferrer">${proxy.source_url_secondary}</a></div>` : ''}
        ${proxy.source_file ? `<div class="list-item"><strong>Fichier source</strong><br>${proxy.source_file}</div>` : ''}
        ${proxy.extraction_method ? `<div class="list-item"><strong>Methode</strong><br>${proxy.extraction_method}</div>` : ''}
        ${proxy.processing_note ? `<div class="list-item"><strong>Note de traitement</strong><br>${proxy.processing_note}</div>` : ''}
        ${proxy.uncertainty_note ? `<div class="list-item"><strong>Incertitude</strong><br>${proxy.uncertainty_note}</div>` : ''}
      `;
    }

    function renderProxyChart(proxy) {
      proxyChart.innerHTML = '';
      const rows = proxy.curve_rows || [];
      if (!rows.length) {
        const emptyLabel = document.createElementNS('http://www.w3.org/2000/svg', 'text');
        emptyLabel.setAttribute('x', '20');
        emptyLabel.setAttribute('y', '28');
        emptyLabel.setAttribute('fill', '#64748b');
        emptyLabel.textContent = 'Aucune courbe disponible pour ce proxy.';
        proxyChart.appendChild(emptyLabel);
        return;
      }

      const width = 620;
      const height = 240;
      const padLeft = 42;
      const padRight = 18;
      const padTop = 18;
      const padBottom = 26;
      const values = rows.flatMap((row) => [Number(row.modeled_compared), Number(row.reference_compared)]);
      const maxValue = Math.max(1, ...values.map((value) => Number.isFinite(value) ? value : 0));
      const xForHour = (hour) => padLeft + (hour / 23) * (width - padLeft - padRight);
      const yForValue = (value) => height - padBottom - (Math.max(0, value) / maxValue) * (height - padTop - padBottom);
      const polylinePoints = (key) => rows.map((row) => `${xForHour(row.hour)},${yForValue(Number(row[key]))}`).join(' ');

      const ns = 'http://www.w3.org/2000/svg';
      const make = (tag, attrs = {}) => {
        const node = document.createElementNS(ns, tag);
        Object.entries(attrs).forEach(([key, value]) => node.setAttribute(key, String(value)));
        return node;
      };

      proxyChart.appendChild(make('rect', { x: 0, y: 0, width, height, fill: 'transparent' }));
      for (let tick = 0; tick <= 4; tick += 1) {
        const value = (maxValue / 4) * tick;
        const y = yForValue(value);
        proxyChart.appendChild(make('line', { x1: padLeft, y1: y, x2: width - padRight, y2: y, stroke: '#d6d3d1', 'stroke-width': 1 }));
        const label = make('text', { x: 8, y: y + 4, fill: '#64748b', 'font-size': 11 });
        label.textContent = value.toFixed(2);
        proxyChart.appendChild(label);
      }
      proxyChart.appendChild(make('line', { x1: padLeft, y1: height - padBottom, x2: width - padRight, y2: height - padBottom, stroke: '#334155', 'stroke-width': 1.5 }));
      proxyChart.appendChild(make('line', { x1: padLeft, y1: padTop, x2: padLeft, y2: height - padBottom, stroke: '#334155', 'stroke-width': 1.5 }));

      [0, 6, 12, 18, 23].forEach((hour) => {
        const x = xForHour(hour);
        proxyChart.appendChild(make('line', { x1: x, y1: height - padBottom, x2: x, y2: height - padBottom + 5, stroke: '#334155', 'stroke-width': 1 }));
        const label = make('text', { x: x - 8, y: height - 6, fill: '#64748b', 'font-size': 11 });
        label.textContent = `h${String(hour).padStart(2, '0')}`;
        proxyChart.appendChild(label);
      });

      proxyChart.appendChild(make('polyline', {
        points: polylinePoints('reference_compared'),
        fill: 'none',
        stroke: '#b91c1c',
        'stroke-width': 2.5,
      }));
      proxyChart.appendChild(make('polyline', {
        points: polylinePoints('modeled_compared'),
        fill: 'none',
        stroke: '#1d4ed8',
        'stroke-width': 2.5,
      }));

      const hourX = xForHour(state.hour);
      proxyChart.appendChild(make('line', {
        x1: hourX,
        y1: padTop,
        x2: hourX,
        y2: height - padBottom,
        stroke: '#0f172a',
        'stroke-width': 1.5,
        'stroke-dasharray': '4 4',
      }));
      const hourLabel = make('text', { x: hourX + 6, y: padTop + 14, fill: '#0f172a', 'font-size': 11, 'font-weight': 700 });
      hourLabel.textContent = `heure lue : h${String(state.hour).padStart(2, '0')}`;
      proxyChart.appendChild(hourLabel);
    }

    function renderProxyComparison() {
      const comparison = state.proxyComparison;
      exportProxyComparisonButton.disabled = !comparison || !(comparison.scenarios || []).length;
      loadProxyComparisonButton.disabled = false;
      proxyComparisonChart.innerHTML = '';

      if (!comparison) {
        proxyComparisonPanel.innerHTML = `<div class="list-item muted">${state.proxyComparisonDirty ? 'Comparaison non lancee pour cette selection.' : 'Aucune comparaison chargee.'}</div>`;
        return;
      }
      const scenarios = comparison.scenarios || [];
      if (!scenarios.length) {
        proxyComparisonPanel.innerHTML = '<div class="list-item muted">Aucune comparaison disponible pour ce jeu de scenarios.</div>';
        return;
      }

      proxyComparisonPanel.innerHTML = scenarios.map((row) => `
        <div class="list-item">
          <strong>${row.scenario_name}</strong><br>
          <span class="badge">${row.scenario_file}</span>
          <span class="status-pill status-${row.status}">${String(row.status).toUpperCase()}</span>
          <span class="badge">corr = ${row.correlation ?? 'n/a'}</span>
          <span class="badge">rmse = ${row.rmse ?? 'n/a'}</span>
          <span class="badge">pic = ${row.peak_hour_gap ?? 'n/a'} h</span>
          ${row.applicable ? '' : `<span class="badge">${row.reason}</span>`}
        </div>
      `).join('');

      renderProxyComparisonChart(comparison);
    }

    function renderProxyComparisonChart(comparison) {
      const scenarios = comparison.scenarios || [];
      if (!scenarios.length) return;

      const width = 620;
      const height = 260;
      const padLeft = 42;
      const padRight = 18;
      const padTop = 18;
      const padBottom = 26;
      const values = scenarios.flatMap((scenario) => [
        ...(scenario.curve_rows || []).map((row) => Number(row.modeled_compared)),
      ]);
      if (comparison.reference_curve_rows?.length) {
        values.push(...comparison.reference_curve_rows.map((row) => Number(row.reference_compared)));
      }
      const maxValue = Math.max(1, ...values.map((value) => Number.isFinite(value) ? value : 0));
      const xForHour = (hour) => padLeft + (hour / 23) * (width - padLeft - padRight);
      const yForValue = (value) => height - padBottom - (Math.max(0, value) / maxValue) * (height - padTop - padBottom);
      const ns = 'http://www.w3.org/2000/svg';
      const make = (tag, attrs = {}) => {
        const node = document.createElementNS(ns, tag);
        Object.entries(attrs).forEach(([key, value]) => node.setAttribute(key, String(value)));
        return node;
      };
      const palette = ['#1d4ed8', '#c2410c', '#0f766e', '#7c3aed', '#b45309', '#be123c'];

      proxyComparisonChart.appendChild(make('rect', { x: 0, y: 0, width, height, fill: 'transparent' }));
      for (let tick = 0; tick <= 4; tick += 1) {
        const value = (maxValue / 4) * tick;
        const y = yForValue(value);
        proxyComparisonChart.appendChild(make('line', { x1: padLeft, y1: y, x2: width - padRight, y2: y, stroke: '#d6d3d1', 'stroke-width': 1 }));
        const label = make('text', { x: 8, y: y + 4, fill: '#64748b', 'font-size': 11 });
        label.textContent = value.toFixed(2);
        proxyComparisonChart.appendChild(label);
      }
      proxyComparisonChart.appendChild(make('line', { x1: padLeft, y1: height - padBottom, x2: width - padRight, y2: height - padBottom, stroke: '#334155', 'stroke-width': 1.5 }));
      proxyComparisonChart.appendChild(make('line', { x1: padLeft, y1: padTop, x2: padLeft, y2: height - padBottom, stroke: '#334155', 'stroke-width': 1.5 }));

      [0, 6, 12, 18, 23].forEach((hour) => {
        const x = xForHour(hour);
        proxyComparisonChart.appendChild(make('line', { x1: x, y1: height - padBottom, x2: x, y2: height - padBottom + 5, stroke: '#334155', 'stroke-width': 1 }));
        const label = make('text', { x: x - 8, y: height - 6, fill: '#64748b', 'font-size': 11 });
        label.textContent = `h${String(hour).padStart(2, '0')}`;
        proxyComparisonChart.appendChild(label);
      });

      if (comparison.reference_curve_rows?.length) {
        const referencePoints = comparison.reference_curve_rows
          .map((row) => `${xForHour(row.hour)},${yForValue(Number(row.reference_compared))}`)
          .join(' ');
        proxyComparisonChart.appendChild(make('polyline', {
          points: referencePoints,
          fill: 'none',
          stroke: '#b91c1c',
          'stroke-width': 2,
          'stroke-dasharray': '6 4',
        }));
      }

      scenarios.forEach((scenario, index) => {
        const color = palette[index % palette.length];
        const points = (scenario.curve_rows || [])
          .map((row) => `${xForHour(row.hour)},${yForValue(Number(row.modeled_compared))}`)
          .join(' ');
        if (!points) return;
        proxyComparisonChart.appendChild(make('polyline', {
          points,
          fill: 'none',
          stroke: color,
          'stroke-width': 2.4,
        }));
      });

      let legendY = 20;
      if (comparison.reference_curve_rows?.length) {
        proxyComparisonChart.appendChild(make('line', { x1: width - 200, y1: legendY, x2: width - 176, y2: legendY, stroke: '#b91c1c', 'stroke-width': 2, 'stroke-dasharray': '6 4' }));
        const refLabel = make('text', { x: width - 170, y: legendY + 4, fill: '#334155', 'font-size': 11 });
        refLabel.textContent = 'reference';
        proxyComparisonChart.appendChild(refLabel);
        legendY += 18;
      }
      scenarios.forEach((scenario, index) => {
        const color = palette[index % palette.length];
        proxyComparisonChart.appendChild(make('line', { x1: width - 200, y1: legendY, x2: width - 176, y2: legendY, stroke: color, 'stroke-width': 2.4 }));
        const label = make('text', { x: width - 170, y: legendY + 4, fill: '#334155', 'font-size': 11 });
        label.textContent = scenario.scenario_name;
        proxyComparisonChart.appendChild(label);
        legendY += 18;
      });
    }

    function renderHouseholdPanel() {
      const householdId = state.memberId !== 'all'
        ? state.data.members.find((member) => member.member_id === state.memberId)?.household_id || 'all'
        : state.householdId;
      if (!state.data || householdId === 'all') {
        householdPanel.innerHTML = '<div class="muted">Selectionne un foyer ou une personne pour afficher la situation familiale.</div>';
        return;
      }
      const household = state.data.households.find((item) => item.household_id === householdId);
      const members = state.data.members.filter((member) => member.household_id === householdId);
      if (!household) {
        householdPanel.innerHTML = '<div class="muted">Foyer introuvable.</div>';
        return;
      }
      householdPanel.innerHTML = `
        <div class="list-item">
          <strong>${household.household_id}</strong><br>
          <span class="badge">${household.size} personnes</span>
          <span class="badge">${household.has_children ? 'avec enfant' : 'sans enfant'}</span>
          <span class="badge">${household.escort_children_count} accompagnement(s)</span>
        </div>
      ` + members.map((member) => `
        <div class="list-item">
          <strong>${member.member_id}</strong><br>
          <span class="badge">${roleName(member.role)}</span>
          <span class="badge">${activityName(member, state.hour)}</span>
          ${member.school_access_status !== 'not_applicable' ? `<span class="badge">ecole : ${member.school_access_status}</span>` : ''}
          ${member.school_distance_m !== null ? `<span class="badge">${Math.round(member.school_distance_m)} m</span>` : ''}
        </div>
      `).join('');
    }

    function renderMemberPanel() {
      if (!state.data || state.memberId === 'all') {
        memberPanel.innerHTML = '<div class="muted">Selectionne une personne pour afficher sa chronologie, son mode d acces et sa matrice horaire.</div>';
        return;
      }
      const member = state.data.members.find((item) => item.member_id === state.memberId);
      if (!member) {
        memberPanel.innerHTML = '<div class="muted">Personne introuvable.</div>';
        return;
      }
      const transitions = buildMovementEvents(member).map((movement) => `
        <div class="list-item">
          <strong>h${String(movement.hour).padStart(2, '0')}</strong> · ${movement.fromLabel} → ${movement.toLabel}
          ${movement.distanceM !== null ? `<span class="badge">${movement.distanceM} m</span>` : ''}
        </div>
      `).join('');
      const hourlyRows = Array.from({ length: 24 }, (_, hour) => `
        <tr class="${hour === state.hour ? 'is-current' : ''}">
          <td><strong>h${String(hour).padStart(2, '0')}</strong></td>
          <td>${member.timeline_states[hour]}</td>
          <td>${member.timeline_labels[hour] || 'n/a'}</td>
          <td>${member.timeline_destinations[hour] || 'n/a'}</td>
          <td>${activityName(member, hour)}</td>
        </tr>
      `).join('');
      memberPanel.innerHTML = `
        <div class="list-item">
          <strong>${member.member_id}</strong><br>
          <span class="badge">${roleName(member.role)}</span>
          <span class="badge">acces ecole : ${member.school_access_status}</span>
          ${member.escort_guardian_id ? `<span class="badge">adulte referent : ${member.escort_guardian_id}</span>` : ''}
        </div>
      `
        + (transitions ? `<div class="list-item"><strong>Changements de lieu</strong></div>${transitions}` : '')
        + `
        <div class="list-item"><strong>Matrice horaire</strong><br><span class="muted">Etat, lieu lu et destination associes pour chaque heure.</span></div>
        <table class="matrix-table">
          <thead>
            <tr>
              <th>Heure</th>
              <th>Etat</th>
              <th>Lieu lu</th>
              <th>Destination</th>
              <th>Resume</th>
            </tr>
          </thead>
          <tbody>${hourlyRows}</tbody>
        </table>`;
    }

    function currentPoint(member) {
      return member.timeline_points[state.hour];
    }

    function haversineDistanceMeters(pointA, pointB) {
      if (!pointA || !pointB) return null;
      const toRad = (value) => (value * Math.PI) / 180;
      const lat1 = toRad(pointA[0]);
      const lat2 = toRad(pointB[0]);
      const dLat = lat2 - lat1;
      const dLon = toRad(pointB[1] - pointA[1]);
      const a = Math.sin(dLat / 2) ** 2
        + Math.cos(lat1) * Math.cos(lat2) * Math.sin(dLon / 2) ** 2;
      return Math.round(6371000 * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a)));
    }

    function buildMovementEvents(member) {
      const events = [];
      for (let hour = 1; hour < member.timeline_points.length; hour += 1) {
        const previousPoint = member.timeline_points[hour - 1];
        const nextPoint = member.timeline_points[hour];
        const previousLabel = activityName(member, hour - 1);
        const nextLabel = activityName(member, hour);
        if (previousLabel === nextLabel && samePoint(previousPoint, nextPoint)) continue;
        events.push({
          hour,
          fromLabel: previousLabel,
          toLabel: nextLabel,
          distanceM: previousPoint && nextPoint ? haversineDistanceMeters(previousPoint, nextPoint) : null,
        });
      }
      return events;
    }

    function buildRouteSegments(member) {
      const segments = [];
      for (let hour = 1; hour < member.timeline_points.length; hour += 1) {
        const startPoint = member.timeline_points[hour - 1];
        const endPoint = member.timeline_points[hour];
        if (!startPoint || !endPoint || samePoint(startPoint, endPoint)) continue;
        segments.push({ hour, startPoint, endPoint });
      }
      return segments;
    }

    function dedupedPath(points) {
      const result = [];
      points.forEach((point) => {
        if (!point) return;
        const last = result[result.length - 1];
        if (!last || last[0] !== point[0] || last[1] !== point[1]) result.push(point);
      });
      return result;
    }

    function webMercator(lat, lon, zoom) {
      const scale = 256 * Math.pow(2, zoom);
      const x = ((lon + 180) / 360) * scale;
      const sinLat = Math.sin((lat * Math.PI) / 180);
      const y = (0.5 - Math.log((1 + sinLat) / (1 - sinLat)) / (4 * Math.PI)) * scale;
      return { x, y };
    }

    function clamp(value, min, max) {
      return Math.min(max, Math.max(min, value));
    }

    function resetMapView() {
      state.mapView.panX = 0;
      state.mapView.panY = 0;
      state.mapView.zoomFactor = 1;
      state.mapView.dragging = false;
      state.mapView.pointerId = null;
      state.mapView.lastX = 0;
      state.mapView.lastY = 0;
      state.mapView.dragDistance = 0;
      mapRoot.classList.remove('is-dragging');
    }

    function computeView() {
      if (!state.data) return null;
      const [[south, west], [north, east]] = state.data.map.bounds;
      const rect = mapRoot.getBoundingClientRect();
      const width = Math.max(1, rect.width);
      const height = Math.max(1, rect.height);
      const zoom = basemapSelect.value === 'satellite' ? 16 : 15;
      const nw = webMercator(north, west, zoom);
      const se = webMercator(south, east, zoom);
      const pad = 36;
      const mapWidth = Math.max(1, se.x - nw.x);
      const mapHeight = Math.max(1, se.y - nw.y);
      const fitScale = Math.min((width - 2 * pad) / mapWidth, (height - 2 * pad) / mapHeight);
      const scale = fitScale * state.mapView.zoomFactor;
      const baseOffsetX = (width - mapWidth * fitScale) / 2;
      const baseOffsetY = (height - mapHeight * fitScale) / 2;
      const offsetX = baseOffsetX + state.mapView.panX;
      const offsetY = baseOffsetY + state.mapView.panY;
      return { width, height, zoom, nw, se, scale, fitScale, offsetX, offsetY, baseOffsetX, baseOffsetY };
    }

    function pointToScreen(point, view) {
      if (!point || !view) return null;
      const world = webMercator(point[0], point[1], view.zoom);
      return [
        (world.x - view.nw.x) * view.scale + view.offsetX,
        (world.y - view.nw.y) * view.scale + view.offsetY,
      ];
    }

    function svgElement(tag, attrs = {}) {
      const node = document.createElementNS('http://www.w3.org/2000/svg', tag);
      Object.entries(attrs).forEach(([key, value]) => node.setAttribute(key, String(value)));
      return node;
    }

    function centerMapOnPoint(point) {
      if (!point || !state.data) return;
      const view = computeView();
      if (!view) return;
      const screenPoint = pointToScreen(point, view);
      if (!screenPoint) return;
      state.mapView.panX += (view.width / 2) - screenPoint[0];
      state.mapView.panY += (view.height / 2) - screenPoint[1];
    }

    function maybeFollowSelectedMember() {
      if (!state.followSelected) return;
      const member = selectedMember();
      if (!member) return;
      centerMapOnPoint(currentPoint(member) || member.home_point);
    }

    function focusMember(memberId) {
      state.memberId = memberId;
      const member = selectedMember();
      if (member) state.householdId = member.household_id || 'all';
      switchPanel('member');
      syncView();
    }

    function pickMemberAt(clientX, clientY) {
      const view = computeView();
      if (!view) return null;
      const rect = mapRoot.getBoundingClientRect();
      const x = clientX - rect.left;
      const y = clientY - rect.top;
      let bestMember = null;
      let bestDistance = Infinity;
      filteredMembers().forEach((member) => {
        const point = pointToScreen(currentPoint(member), view);
        if (!point) return;
        const distance = Math.hypot(point[0] - x, point[1] - y);
        const hitRadius = state.memberId === member.member_id ? 16 : 12;
        if (distance <= hitRadius && distance < bestDistance) {
          bestDistance = distance;
          bestMember = member;
        }
      });
      return bestMember;
    }

    function tileTemplate(mode) {
      if (mode === 'satellite') return 'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}';
      return 'https://tile.openstreetmap.org/{z}/{x}/{y}.png';
    }

    function initMap() {
      resetMapView();
      mapTiles.innerHTML = '';
      mapOverlay.innerHTML = '';
      mapOverlay.setAttribute('viewBox', '0 0 1 1');
      mapOverlay.setAttribute('width', '1');
      mapOverlay.setAttribute('height', '1');
      mapBadge.textContent = 'Carte prete. Glisse pour deplacer la vue et utilise la molette pour zoomer.';
    }

    function bindMapInteractions() {
      mapRoot.addEventListener('pointerdown', (event) => {
        if (event.button !== 0) return;
        state.mapView.dragging = true;
        state.mapView.pointerId = event.pointerId;
        state.mapView.lastX = event.clientX;
        state.mapView.lastY = event.clientY;
        state.mapView.dragDistance = 0;
        mapRoot.classList.add('is-dragging');
        mapRoot.setPointerCapture(event.pointerId);
      });

      mapRoot.addEventListener('pointermove', (event) => {
        if (!state.mapView.dragging || state.mapView.pointerId !== event.pointerId) return;
        const dx = event.clientX - state.mapView.lastX;
        const dy = event.clientY - state.mapView.lastY;
        state.mapView.dragDistance += Math.hypot(dx, dy);
        state.mapView.panX += dx;
        state.mapView.panY += dy;
        state.mapView.lastX = event.clientX;
        state.mapView.lastY = event.clientY;
        renderMap();
      });

      function stopDragging(event) {
        if (state.mapView.pointerId !== null && event.pointerId === state.mapView.pointerId) {
          if (state.mapView.dragDistance < 6) {
            const hitMember = pickMemberAt(event.clientX, event.clientY);
            if (hitMember) {
              focusMember(hitMember.member_id);
            }
          }
          state.mapView.dragging = false;
          state.mapView.pointerId = null;
          state.mapView.dragDistance = 0;
          mapRoot.classList.remove('is-dragging');
        }
      }

      mapRoot.addEventListener('pointerup', stopDragging);
      mapRoot.addEventListener('pointercancel', stopDragging);
      mapRoot.addEventListener('pointerleave', stopDragging);

      mapRoot.addEventListener('wheel', (event) => {
        if (!state.data) return;
        event.preventDefault();
        const rect = mapRoot.getBoundingClientRect();
        const cursorX = event.clientX - rect.left;
        const cursorY = event.clientY - rect.top;
        const view = computeView();
        if (!view) return;
        const oldZoomFactor = state.mapView.zoomFactor;
        const factor = event.deltaY < 0 ? 1.14 : 1 / 1.14;
        const newZoomFactor = clamp(oldZoomFactor * factor, 0.8, 12);
        const worldX = (cursorX - view.baseOffsetX - state.mapView.panX) / (view.fitScale * oldZoomFactor);
        const worldY = (cursorY - view.baseOffsetY - state.mapView.panY) / (view.fitScale * oldZoomFactor);
        state.mapView.zoomFactor = newZoomFactor;
        state.mapView.panX = cursorX - worldX * view.fitScale * newZoomFactor - view.baseOffsetX;
        state.mapView.panY = cursorY - worldY * view.fitScale * newZoomFactor - view.baseOffsetY;
        renderMap();
      }, { passive: false });
    }

    function renderTiles(view) {
      mapTiles.innerHTML = '';
      if (!view) return;
      const tileSize = 256;
      const template = tileTemplate(basemapSelect.value);
      const minTileX = Math.floor(view.nw.x / tileSize);
      const maxTileX = Math.floor(view.se.x / tileSize);
      const minTileY = Math.floor(view.nw.y / tileSize);
      const maxTileY = Math.floor(view.se.y / tileSize);
      for (let x = minTileX; x <= maxTileX; x += 1) {
        for (let y = minTileY; y <= maxTileY; y += 1) {
          const img = document.createElement('img');
          img.alt = '';
          img.src = template.replace('{z}', String(view.zoom)).replace('{x}', String(x)).replace('{y}', String(y));
          img.style.left = `${(x * tileSize - view.nw.x) * view.scale + view.offsetX}px`;
          img.style.top = `${(y * tileSize - view.nw.y) * view.scale + view.offsetY}px`;
          img.style.width = `${tileSize * view.scale}px`;
          img.style.height = `${tileSize * view.scale}px`;
          img.onerror = () => { img.style.display = 'none'; };
          mapTiles.appendChild(img);
        }
      }
      mapBadge.textContent = basemapSelect.value === 'satellite'
        ? 'Fond satellite si les tuiles externes sont accessibles. Glisse pour deplacer la vue et utilise la molette pour zoomer.'
        : 'Fond plan si les tuiles externes sont accessibles. Glisse pour deplacer la vue et utilise la molette pour zoomer.';
    }

    function renderMap() {
      const view = computeView();
      mapOverlay.innerHTML = '';
      if (!view) return;
      renderTiles(view);
      mapOverlay.setAttribute('viewBox', `0 0 ${view.width} ${view.height}`);
      mapOverlay.setAttribute('width', `${view.width}`);
      mapOverlay.setAttribute('height', `${view.height}`);
      mapOverlay.appendChild(svgElement('rect', { x: 0, y: 0, width: view.width, height: view.height, fill: 'rgba(255,255,255,0.06)' }));
      const focusedMember = selectedMember();

      const members = filteredMembers();
      const household = state.householdId !== 'all'
        ? state.data.households.find((item) => item.household_id === state.householdId)
        : null;
      const homePoint = household ? pointToScreen(household.home_point, view) : null;
      const placeColors = {
        plage: '#ea580c',
        hebergement: '#db2777',
        culte: '#7c3aed',
        enseignement: '#0f766e',
        industrie: '#475569',
        travail_services: '#2563eb',
        sport_loisir: '#059669',
        autre_exogene: '#9a3412',
      };
      const visiblePlaces = (state.data?.map_exogenous_places || [])
        .map((place) => ({ ...place, count: Number(place.hourly_counts?.[state.hour] || 0) }))
        .filter((place) => place.count > 0);

      visiblePlaces.forEach((place) => {
        const point = pointToScreen(place.point, view);
        if (!point) return;
        const color = placeColors[place.type] || '#334155';
        const radius = Math.max(7, Math.min(28, 5 + Math.sqrt(place.count) / 2.2));
        mapOverlay.appendChild(svgElement('circle', {
          cx: point[0],
          cy: point[1],
          r: radius,
          fill: color,
          'fill-opacity': place.type === 'plage' ? 0.24 : 0.18,
          stroke: color,
          'stroke-width': place.type === 'plage' ? 2.2 : 1.6,
          'stroke-opacity': 0.85,
        }));
        mapOverlay.appendChild(svgElement('circle', {
          cx: point[0],
          cy: point[1],
          r: Math.max(3, radius * 0.28),
          fill: color,
          'fill-opacity': 0.88,
          stroke: '#ffffff',
          'stroke-width': 1.1,
        }));
        if (place.count >= 25 || place.type === 'plage') {
          const label = svgElement('text', {
            x: point[0],
            y: point[1] - radius - 6,
            'text-anchor': 'middle',
            'font-size': 11,
            'font-weight': 700,
            fill: color,
          });
          label.textContent = `${placeTypeName(place.type)} ${place.count}`;
          mapOverlay.appendChild(label);
        }
        const title = svgElement('title');
        title.textContent = `${placeTypeName(place.type)} · ${place.label} · ${place.count} personnes a h${String(state.hour).padStart(2, '0')}`;
        const hit = svgElement('circle', {
          cx: point[0],
          cy: point[1],
          r: radius + 2,
          fill: 'transparent',
        });
        hit.appendChild(title);
        mapOverlay.appendChild(hit);
      });

      if (focusedMember) {
        const defs = svgElement('defs');
        const marker = svgElement('marker', {
          id: 'routeArrow',
          markerWidth: 10,
          markerHeight: 10,
          refX: 9,
          refY: 5,
          orient: 'auto',
          markerUnits: 'strokeWidth',
        });
        marker.appendChild(svgElement('path', {
          d: 'M 0 0 L 10 5 L 0 10 z',
          fill: focusedMember.role_color,
          'fill-opacity': 0.95,
        }));
        defs.appendChild(marker);
        mapOverlay.appendChild(defs);

        const path = dedupedPath(focusedMember.timeline_points).map((point) => pointToScreen(point, view)).filter(Boolean);
        if (path.length >= 2) {
          mapOverlay.appendChild(svgElement('polyline', {
            points: path.map((item) => `${item[0]},${item[1]}`).join(' '),
            fill: 'none',
            stroke: focusedMember.role_color,
            'stroke-width': 2.5,
            'stroke-opacity': 0.24,
            'stroke-dasharray': '5 4',
          }));
        }
        buildRouteSegments(focusedMember).forEach((segment) => {
          const start = pointToScreen(segment.startPoint, view);
          const end = pointToScreen(segment.endPoint, view);
          if (!start || !end) return;
          mapOverlay.appendChild(svgElement('line', {
            x1: start[0],
            y1: start[1],
            x2: end[0],
            y2: end[1],
            stroke: focusedMember.role_color,
            'stroke-width': 3.5,
            'stroke-opacity': 0.88,
            'marker-end': 'url(#routeArrow)',
          }));
          const midX = (start[0] + end[0]) / 2;
          const midY = (start[1] + end[1]) / 2;
          mapOverlay.appendChild(svgElement('circle', {
            cx: midX,
            cy: midY,
            r: 10,
            fill: 'rgba(255,252,246,0.92)',
            stroke: focusedMember.role_color,
            'stroke-width': 1.5,
          }));
          const label = svgElement('text', {
            x: midX,
            y: midY + 4,
            'text-anchor': 'middle',
            'font-size': 10,
            'font-weight': 700,
            fill: '#12252b',
          });
          label.textContent = `h${String(segment.hour).padStart(2, '0')}`;
          mapOverlay.appendChild(label);
        });
      }

      if (homePoint) {
        mapOverlay.appendChild(svgElement('circle', {
          cx: homePoint[0], cy: homePoint[1], r: 7, fill: '#ffffff', stroke: '#111827', 'stroke-width': 2,
        }));
      }

      members.forEach((member) => {
        const point = pointToScreen(currentPoint(member), view);
        if (!point) return;
        if (homePoint) {
          const line = svgElement('line', {
            x1: homePoint[0],
            y1: homePoint[1],
            x2: point[0],
            y2: point[1],
            stroke: member.role_color,
            'stroke-width': member.role === 'scolaire' ? 3 : 2,
            'stroke-opacity': 0.42,
          });
          if (member.escort_mode === 'escort') line.setAttribute('stroke-dasharray', '6 5');
          mapOverlay.appendChild(line);
        }
        const circle = svgElement('circle', {
          cx: point[0],
          cy: point[1],
          r: state.memberId === member.member_id ? 8 : 5,
          fill: member.role_color,
          stroke: '#ffffff',
          'stroke-width': 1.5,
          'fill-opacity': 0.92,
        });
        const title = svgElement('title');
        title.textContent = `${member.member_id} · ${roleName(member.role)} · ${activityName(member, state.hour)} · acces ${member.school_access_status}`;
        circle.appendChild(title);
        mapOverlay.appendChild(circle);
      });
      mapBadge.textContent = focusedMember
        ? `${focusedMember.member_id} ${state.followSelected ? 'reste centre automatiquement' : 'est selectionne'}. Clique une autre personne pour changer de cible.`
        : 'Clique une personne pour afficher sa journee. Les bulles indiquent la population exogene visible a l heure lue.';
    }

    function updateHour(hour) {
      state.hour = Number(hour);
      hourSlider.value = state.hour;
      hourLabel.textContent = `h${String(state.hour).padStart(2, '0')}`;
      maybeFollowSelectedMember();
      renderStats();
      renderHouseholdPanel();
      renderMemberPanel();
      renderProxyValidation();
      renderProxyComparison();
      renderMap();
    }

    function syncView() {
      populateControls();
      updateHour(state.hour);
    }

    function bindEvents() {
      window.addEventListener('resize', () => renderMap());
      basemapSelect.addEventListener('change', () => renderMap());
      sectionTabs.forEach((button) => {
        button.addEventListener('click', () => switchPanel(button.dataset.panelTarget));
      });
      followMemberButton.addEventListener('click', () => {
        state.followSelected = !state.followSelected;
        if (state.followSelected) maybeFollowSelectedMember();
        syncView();
      });
      resetMapViewButton.addEventListener('click', () => {
        resetMapView();
        maybeFollowSelectedMember();
        renderMap();
      });
      roleSelect.addEventListener('change', () => {
        state.role = roleSelect.value;
        state.householdId = 'all';
        state.memberId = 'all';
        syncView();
      });
      scenarioSelect.addEventListener('change', async () => {
        if (!state.data || scenarioSelect.value === state.data.selected_scenario_id) return;
        scenarioSelect.disabled = true;
        refreshButton.disabled = true;
        setLoadingState('Chargement du scenario...');
        try {
          state.data = await fetchJsonOrThrow('/api/scenario', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ scenario_id: scenarioSelect.value }),
          });
          state.role = 'all';
          state.householdId = 'all';
          state.memberId = 'all';
          state.proxyId = '';
          markProxyComparisonDirty('Comparaison a relancer pour le nouveau scenario.');
          state.hour = state.data.reference_hour;
          resetMapView();
          syncView();
        } catch (error) {
          reportActionError(error, 'Le changement de scenario a echoue.');
          scenarioSelect.value = state.data?.selected_scenario_id || scenarioSelect.value;
        } finally {
          scenarioSelect.disabled = false;
          refreshButton.disabled = false;
        }
      });
      householdSelect.addEventListener('change', () => {
        state.householdId = householdSelect.value;
        state.memberId = 'all';
        switchPanel('household');
        syncView();
      });
      memberSelect.addEventListener('change', () => {
        if (memberSelect.value === 'all') {
          state.memberId = 'all';
          syncView();
          return;
        }
        focusMember(memberSelect.value);
      });
      proxySelect.addEventListener('change', () => {
        state.proxyId = proxySelect.value;
        switchPanel('proxy');
        renderProxyValidation();
        markProxyComparisonDirty('Comparaison a lancer pour le proxy selectionne.');
      });
      proxyStatusFilter.addEventListener('change', () => {
        state.proxyStatusFilter = proxyStatusFilter.value;
        switchPanel('proxy');
        renderProxyValidation();
      });
      proxyListPanel.addEventListener('click', (event) => {
        const target = event.target.closest('[data-proxy-id]');
        if (!target) return;
        state.proxyId = target.getAttribute('data-proxy-id') || '';
        switchPanel('proxy');
        renderProxyValidation();
        markProxyComparisonDirty('Comparaison a lancer pour le proxy selectionne.');
      });
      loadProxyComparisonButton.addEventListener('click', () => {
        switchPanel('proxy');
        void loadProxyComparison();
      });
      exportProxySummaryButton.addEventListener('click', () => {
        const scenarioSlug = (state.data?.scenario_name || 'scenario').replace(/[^a-z0-9_-]+/gi, '_');
        downloadCsv(`${scenarioSlug}_proxy_summary.csv`, proxySummaryRows());
      });
      exportProxyCurvesButton.addEventListener('click', () => {
        const scenarioSlug = (state.data?.scenario_name || 'scenario').replace(/[^a-z0-9_-]+/gi, '_');
        downloadCsv(`${scenarioSlug}_proxy_curves.csv`, proxyCurveRows());
      });
      exportProxyComparisonButton.addEventListener('click', () => {
        const scenarioSlug = (state.data?.scenario_name || 'scenario').replace(/[^a-z0-9_-]+/gi, '_');
        downloadCsv(`${scenarioSlug}_proxy_comparison.csv`, proxyComparisonRows());
      });
      proxyComparisonSetSelect.addEventListener('change', () => {
        state.proxyComparisonSetId = proxyComparisonSetSelect.value;
        switchPanel('proxy');
        markProxyComparisonDirty('Comparaison a relancer pour ce jeu de scenarios.');
      });
      hourSlider.addEventListener('input', () => updateHour(hourSlider.value));

      playButton.addEventListener('click', () => {
        state.playing = !state.playing;
        playButton.textContent = state.playing ? 'Pause' : 'Lecture';
        if (state.playing) {
          state.timer = window.setInterval(() => updateHour((state.hour + 1) % 24), 900);
        } else if (state.timer) {
          window.clearInterval(state.timer);
          state.timer = null;
        }
      });

      refreshButton.addEventListener('click', async () => {
        refreshButton.disabled = true;
        scenarioSelect.disabled = true;
        refreshButton.textContent = 'Rechargement...';
        setLoadingState('Recalcul du scenario en cours...');
        try {
          await loadData(true);
        } catch (error) {
          reportActionError(error, 'Le rechargement du scenario a echoue.');
        } finally {
          refreshButton.disabled = false;
          scenarioSelect.disabled = false;
          refreshButton.textContent = 'Recharger le scenario';
        }
      });
    }

    async function loadData(refresh = false) {
      state.data = await fetchJsonOrThrow(`/api/state${refresh ? '?refresh=1' : ''}`);
      state.hour = state.data.reference_hour;
      if (!(state.data.proxy_validation?.proxies || []).some((proxy) => proxy.proxy_id === state.proxyId)) {
        state.proxyId = state.data.proxy_validation?.proxies?.[0]?.proxy_id || '';
      }
      if (!(state.data.proxy_comparison_sets || []).some((item) => item.id === state.proxyComparisonSetId)) {
        state.proxyComparisonSetId = state.data.proxy_comparison_sets?.[0]?.id || 'root_catalog';
      }
      resetMapView();
      syncView();
      markProxyComparisonDirty(refresh ? 'Comparaison a relancer apres rechargement.' : 'Comparaison disponible sur demande.');
    }

    async function bootstrap() {
      initMap();
      bindMapInteractions();
      bindEvents();
      setLoadingState('Chargement du scenario initial...');
      try {
        await loadData(false);
      } catch (error) {
        reportActionError(error, 'Le chargement initial a echoue.');
      }
    }

    bootstrap();
  </script>
</body>
</html>
"""


class _ExplorerState:
    def __init__(self, config_path: str | Path):
        self.project_root = PROJECT_ROOT
        self.config_path = Path(config_path).resolve()
        self._lock = threading.Lock()
        self._scenario_catalog = discover_root_scenarios(self.project_root, self.config_path)
        self._scenario_paths = {
            scenario["id"]: Path(scenario["config_path"]).resolve()
            for scenario in self._scenario_catalog
        }
        self._current_scenario_id = _scenario_id_from_path(self.config_path, self.project_root)
        if self._current_scenario_id not in self._scenario_paths:
            self._scenario_paths[self._current_scenario_id] = self.config_path
            self._scenario_catalog.append(
                {
                    "id": self._current_scenario_id,
                    "file_name": self.config_path.name,
                    "scenario_name": self.config_path.stem,
                    "label": f"{self.config_path.stem} ({self.config_path.name})",
                    "config_path": str(self.config_path),
                }
            )
        self._current_config = load_config(self._scenario_paths[self._current_scenario_id])
        self._gdf: gpd.GeoDataFrame | None = None
        self._payload: dict[str, Any] | None = None
        self._proxy_eval_cache: dict[str, tuple[pd.DataFrame, pd.DataFrame]] = {}

    def _comparison_sets(self) -> list[dict[str, Any]]:
        return _comparison_set_descriptors(
            self._current_config,
            self.config_path,
            self._scenario_catalog,
            self.project_root,
        )

    def _with_catalog(self, payload: dict[str, Any]) -> dict[str, Any]:
        return {
            **payload,
            "available_scenarios": self._scenario_catalog,
            "proxy_comparison_sets": self._comparison_sets(),
            "selected_scenario_id": self._current_scenario_id,
            "selected_scenario_file": self._scenario_paths[self._current_scenario_id].name,
        }

    def _evaluate_proxy_scenario(
        self,
        scenario_id: str,
        scenario_path: str | Path | None = None,
    ) -> tuple[pd.DataFrame, pd.DataFrame]:
        resolved_path = Path(scenario_path).resolve() if scenario_path is not None else self._scenario_paths.get(scenario_id)
        if resolved_path is None:
            raise ValueError(f"Scenario inconnu pour comparaison: {scenario_id}")
        cache_key = str(resolved_path)
        with self._lock:
            cached = self._proxy_eval_cache.get(cache_key)
        if cached is not None:
            return cached
        config = load_config(resolved_path)
        gdf = run_pipeline(config)
        evaluated = evaluate_temporal_proxies(gdf, config)
        with self._lock:
            return self._proxy_eval_cache.setdefault(cache_key, evaluated)

    def compare_proxy(self, proxy_id: str, scenario_set_id: str) -> dict[str, Any]:
        with self._lock:
            comparison_sets = {item["id"]: item for item in self._comparison_sets()}
            selected_set = comparison_sets.get(scenario_set_id) or comparison_sets.get("root_catalog")
        if selected_set is None:
            return {
                "set_id": scenario_set_id,
                "set_label": scenario_set_id,
                "proxy_id": proxy_id,
                "proxy_label": proxy_id,
                "reference_curve_rows": [],
                "scenarios": [],
            }

        proxy_label = proxy_id
        scenarios_payload: list[dict[str, Any]] = []
        reference_curve_rows: list[dict[str, Any]] = []

        for entry in selected_set["entries"]:
            scenario_id = str(entry["scenario_id"])
            scenario_path = Path(str(entry["config_path"])).resolve()
            summary_df, curves_df = self._evaluate_proxy_scenario(scenario_id, scenario_path)
            summary_row = summary_df[summary_df["proxy_id"] == proxy_id]
            if summary_row.empty:
                continue
            row = summary_row.iloc[0]
            curve_rows = curves_df[curves_df["proxy_id"] == proxy_id].sort_values("hour")
            proxy_label = str(row.get("label", proxy_label))
            scenario_name = str(row.get("scenario_name", entry["label"]))
            scenario_payload = {
                "scenario_id": scenario_id,
                "scenario_name": str(entry.get("label") or scenario_name),
                "scenario_file": str(entry.get("file_name") or scenario_path.name),
                "status": str(row.get("status", "info")),
                "applicable": bool(row.get("applicable", True)),
                "reason": str(row.get("reason", "evaluated")),
                "correlation": None if pd.isna(row.get("correlation")) else float(row.get("correlation")),
                "rmse": None if pd.isna(row.get("rmse")) else float(row.get("rmse")),
                "mae": None if pd.isna(row.get("mae")) else float(row.get("mae")),
                "peak_hour_gap": None if pd.isna(row.get("peak_hour_gap")) else int(row.get("peak_hour_gap")),
                "source_name": str(row.get("source_name", "")),
                "extraction_date": str(row.get("extraction_date", "")),
                "confidence": str(row.get("confidence", "")),
                "curve_rows": curve_rows.to_dict(orient="records"),
            }
            scenarios_payload.append(scenario_payload)
            if not reference_curve_rows and not curve_rows.empty:
                reference_curve_rows = [
                    {
                        "hour": int(item["hour"]),
                        "reference_compared": float(item["reference_compared"]),
                    }
                    for item in curve_rows.to_dict(orient="records")
                ]

        return {
            "set_id": str(selected_set["id"]),
            "set_label": str(selected_set["label"]),
            "proxy_id": proxy_id,
            "proxy_label": proxy_label,
            "reference_curve_rows": reference_curve_rows,
            "scenarios": scenarios_payload,
        }

    def payload(self, refresh: bool = False) -> dict[str, Any]:
        with self._lock:
            if refresh or self._payload is None or self._gdf is None:
                if refresh:
                    self._proxy_eval_cache.pop(str(self._scenario_paths[self._current_scenario_id]), None)
                self._gdf = run_pipeline(self._current_config)
                self._payload = self._with_catalog(build_realtime_explorer_payload(self._gdf, self._current_config))
            return self._payload

    def select_scenario(self, scenario_id: str) -> dict[str, Any]:
        with self._lock:
            if scenario_id not in self._scenario_paths:
                raise ValueError(f"Scenario inconnu: {scenario_id}")
            self._current_scenario_id = scenario_id
            self.config_path = self._scenario_paths[scenario_id]
            self._current_config = load_config(self.config_path)
            self._gdf = run_pipeline(self._current_config)
            self._proxy_eval_cache.pop(str(self.config_path), None)
            self._payload = self._with_catalog(build_realtime_explorer_payload(self._gdf, self._current_config))
            return self._payload


def _handler_factory(state: _ExplorerState):
    class ExplorerHandler(BaseHTTPRequestHandler):
        def _send_json(self, payload: dict[str, Any], status_code: int = 200) -> None:
            data = json.dumps(_make_json_safe(payload), allow_nan=False).encode("utf-8")
            self.send_response(status_code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def _send_html(self, html: str) -> None:
            data = html.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            try:
                if parsed.path == "/api/state":
                    refresh = parse_qs(parsed.query).get("refresh", ["0"])[0] == "1"
                    self._send_json(state.payload(refresh=refresh))
                    return
                if parsed.path in {"/", "/index.html"}:
                    self._send_html(render_realtime_explorer_html())
                    return
                self.send_error(404, "Resource not found")
            except Exception as exc:  # pragma: no cover - HTTP safety net
                logger.exception("Erreur HTTP GET %s", parsed.path)
                self._send_json({"error": str(exc)}, status_code=500)

        def do_POST(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            try:
                if parsed.path == "/api/scenario":
                    content_length = int(self.headers.get("Content-Length", "0"))
                    raw_body = self.rfile.read(content_length) if content_length > 0 else b"{}"
                    payload = json.loads(raw_body.decode("utf-8") or "{}")
                    scenario_id = str(payload.get("scenario_id", "")).strip()
                    self._send_json(state.select_scenario(scenario_id))
                    return
                if parsed.path == "/api/proxy-compare":
                    content_length = int(self.headers.get("Content-Length", "0"))
                    raw_body = self.rfile.read(content_length) if content_length > 0 else b"{}"
                    payload = json.loads(raw_body.decode("utf-8") or "{}")
                    proxy_id = str(payload.get("proxy_id", "")).strip()
                    scenario_set_id = str(payload.get("scenario_set_id", "root_catalog")).strip() or "root_catalog"
                    self._send_json(state.compare_proxy(proxy_id, scenario_set_id))
                    return
                self.send_error(404, "Resource not found")
            except Exception as exc:  # pragma: no cover - HTTP safety net
                logger.exception("Erreur HTTP POST %s", parsed.path)
                self._send_json({"error": str(exc)}, status_code=500)

        def log_message(self, format: str, *args) -> None:  # noqa: A003
            return

    return ExplorerHandler


def serve_realtime_explorer(config_path: str | Path, host: str = "127.0.0.1", port: int = 8765) -> ThreadingHTTPServer:
    state = _ExplorerState(config_path)
    return ThreadingHTTPServer((host, port), _handler_factory(state))
