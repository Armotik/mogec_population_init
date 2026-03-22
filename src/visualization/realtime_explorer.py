"""
Serveur web local pour explorer les profils et trajectoires en temps quasi reel.
"""

from __future__ import annotations

from collections import defaultdict
from copy import deepcopy
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import threading
from typing import Any
from urllib.parse import parse_qs, urlparse

import geopandas as gpd
import pandas as pd
from pyproj import Transformer
import yaml

from src.core.temporal import build_member_timelines, generer_matrice_horaire
from src.pipeline import load_config, run_pipeline


ROLE_COLORS = {
    "scolaire": "#0f766e",
    "senior": "#6d28d9",
    "actif_local": "#c2410c",
    "actif_navetteur": "#1d4ed8",
    "inactif": "#64748b",
}

EDITABLE_CONFIG_FIELDS = [
    {
        "path": "scenario.day_of_week",
        "label": "Jour du scenario",
        "type": "select",
        "options": ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi", "Dimanche"],
    },
    {
        "path": "scenario.is_school_holiday",
        "label": "Vacances scolaires",
        "type": "boolean",
    },
    {
        "path": "scenario.reference_hour",
        "label": "Heure de reference T0",
        "type": "integer",
        "min": 0,
        "max": 23,
        "step": 1,
    },
    {
        "path": "scenario.temporal_context.weather_index",
        "fallback_path": "temporal_model.scenario_context.weather_index",
        "label": "Indice meteo",
        "type": "number",
        "min": 0,
        "max": 1,
        "step": 0.1,
    },
    {
        "path": "scenario.temporal_context.alert_level",
        "fallback_path": "temporal_model.scenario_context.alert_level",
        "label": "Niveau d'alerte",
        "type": "number",
        "min": 0,
        "max": 1,
        "step": 0.1,
    },
    {
        "path": "scenario.residences.alpha_domicile",
        "label": "Presence residentielle a T0",
        "type": "number",
        "min": 0,
        "max": 1,
        "step": 0.05,
    },
    {
        "path": "non_residential_model.accommodation.tau_occupation",
        "label": "Occupation hebergements",
        "type": "number",
        "min": 0,
        "max": 1,
        "step": 0.05,
    },
    {
        "path": "temporal_model.household_dynamics.school_walk_max_distance_m",
        "label": "Distance max ecole a pied (m)",
        "type": "integer",
        "min": 100,
        "max": 3000,
        "step": 50,
    },
    {
        "path": "temporal_model.household_dynamics.school_pickup_overlap_hours",
        "label": "Tolerance reprise parent (h)",
        "type": "integer",
        "min": 0,
        "max": 4,
        "step": 1,
    },
]

PAYLOAD_ONLY_PATHS = {
    "scenario.reference_hour",
}

TEMPORAL_REBUILD_PREFIXES = (
    "scenario.day_of_week",
    "scenario.is_school_holiday",
    "scenario.temporal_context",
    "temporal_model.scenario_context",
    "temporal_model.household_dynamics",
)


def _deep_get(config: dict[str, Any], path: str, default: Any = None) -> Any:
    current: Any = config
    for key in path.split("."):
        if not isinstance(current, dict) or key not in current:
            return default
        current = current[key]
    return current


def _deep_set(config: dict[str, Any], path: str, value: Any) -> None:
    current = config
    parts = path.split(".")
    for key in parts[:-1]:
        next_value = current.get(key)
        if not isinstance(next_value, dict):
            next_value = {}
            current[key] = next_value
        current = next_value
    current[parts[-1]] = value


def _diff_config_paths(before: Any, after: Any, prefix: str = "") -> set[str]:
    if isinstance(before, dict) and isinstance(after, dict):
        changed: set[str] = set()
        for key in set(before) | set(after):
            child_prefix = f"{prefix}.{key}" if prefix else str(key)
            if key not in before or key not in after:
                changed.add(child_prefix)
                continue
            changed.update(_diff_config_paths(before[key], after[key], child_prefix))
        return changed
    if isinstance(before, list) and isinstance(after, list):
        return {prefix} if before != after else set()
    return {prefix} if before != after else set()


def _classify_rebuild_mode(changed_paths: set[str], has_cached_gdf: bool) -> str:
    if not has_cached_gdf:
        return "full"
    if not changed_paths:
        return "payload_only"
    if changed_paths.issubset(PAYLOAD_ONLY_PATHS):
        return "payload_only"
    if all(
        any(path == prefix or path.startswith(f"{prefix}.") for prefix in TEMPORAL_REBUILD_PREFIXES)
        or path in PAYLOAD_ONLY_PATHS
        for path in changed_paths
    ):
        return "temporal_only"
    return "full"


def _deep_merge_dicts(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge_dicts(merged[key], value)
        else:
            merged[key] = deepcopy(value)
    return merged


def get_editable_config_fields(config: dict[str, Any]) -> list[dict[str, Any]]:
    fields: list[dict[str, Any]] = []
    for field in EDITABLE_CONFIG_FIELDS:
        value = _deep_get(config, field["path"], default=None)
        if value is None and field.get("fallback_path"):
            value = _deep_get(config, field["fallback_path"], default=None)
        fields.append({**field, "value": value})
    return fields


def apply_config_updates(config: dict[str, Any], updates: dict[str, Any]) -> dict[str, Any]:
    updated = deepcopy(config)
    field_types = {field["path"]: field["type"] for field in EDITABLE_CONFIG_FIELDS}
    for path, raw_value in updates.items():
        field_type = field_types.get(path)
        if field_type == "boolean":
            value = bool(raw_value)
        elif field_type == "integer":
            value = int(raw_value)
        elif field_type == "number":
            value = float(raw_value)
        else:
            value = raw_value
        _deep_set(updated, path, value)
    return updated


def build_config_patch_yaml(config: dict[str, Any]) -> str:
    patch = {
        "scenario": {
            "day_of_week": _deep_get(config, "scenario.day_of_week"),
            "is_school_holiday": _deep_get(config, "scenario.is_school_holiday"),
            "reference_hour": _deep_get(config, "scenario.reference_hour"),
            "temporal_context": {
                "weather_index": _deep_get(
                    config,
                    "scenario.temporal_context.weather_index",
                    _deep_get(config, "temporal_model.scenario_context.weather_index"),
                ),
                "alert_level": _deep_get(
                    config,
                    "scenario.temporal_context.alert_level",
                    _deep_get(config, "temporal_model.scenario_context.alert_level"),
                ),
            },
            "residences": {
                "alpha_domicile": _deep_get(config, "scenario.residences.alpha_domicile"),
            },
        },
        "non_residential_model": {
            "accommodation": {
                "tau_occupation": _deep_get(config, "non_residential_model.accommodation.tau_occupation"),
            },
        },
        "temporal_model": {
            "household_dynamics": {
                "school_walk_max_distance_m": _deep_get(config, "temporal_model.household_dynamics.school_walk_max_distance_m"),
                "school_pickup_overlap_hours": _deep_get(config, "temporal_model.household_dynamics.school_pickup_overlap_hours"),
            },
        },
    }
    return yaml.safe_dump(patch, sort_keys=False, allow_unicode=True)


def apply_yaml_patch(config: dict[str, Any], yaml_patch: str) -> dict[str, Any]:
    if not yaml_patch.strip():
        return deepcopy(config)
    parsed = yaml.safe_load(yaml_patch)
    if parsed is None:
        return deepcopy(config)
    if not isinstance(parsed, dict):
        raise ValueError("Le patch YAML doit representer un dictionnaire.")
    return _deep_merge_dicts(config, parsed)


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


def build_realtime_explorer_payload(gdf_model: gpd.GeoDataFrame, config: dict) -> dict[str, Any]:
    member_timelines = build_member_timelines(gdf_model, config)
    if member_timelines.empty:
        raise ValueError("Aucune trajectoire individuelle n'a pu etre reconstruite.")

    building_lookup = gdf_model.set_index("building_id")
    transformer = Transformer.from_crs(gdf_model.crs, "EPSG:4326", always_xy=True)

    building_points: dict[str, list[float]] = {}
    for building_id, row in building_lookup.iterrows():
        centroid = row.geometry.centroid
        building_points[str(building_id)] = _to_latlon([float(centroid.x), float(centroid.y)], transformer)

    members_payload: list[dict[str, Any]] = []
    households_index: dict[str, dict[str, Any]] = {}
    school_access_summary: dict[str, int] = defaultdict(int)

    for _, row in member_timelines.iterrows():
        home_building_id = str(row["home_building_id"])
        home_point = building_points.get(home_building_id)
        assigned_destination_id = row["assigned_destination_id"]
        assigned_destination_point = (
            building_points.get(str(assigned_destination_id))
            if assigned_destination_id not in {"DOMICILE", "EXTERIEUR", "None", None}
            else None
        )

        timeline_points = []
        timeline_labels = []
        timeline_usages = []
        for destination_id in row["timeline_destinations"]:
            label, usage = _destination_descriptor(destination_id, building_lookup)
            timeline_labels.append(label)
            timeline_usages.append(usage)
            if destination_id == "DOMICILE":
                timeline_points.append(home_point)
            elif destination_id in {"EXTERIEUR", "None", None}:
                timeline_points.append(None)
            else:
                timeline_points.append(building_points.get(str(destination_id)))

        member_payload = {
            "household_id": str(row.get("household_id") or ""),
            "member_id": str(row["member_id"]),
            "role": str(row["role"]),
            "role_color": ROLE_COLORS.get(str(row["role"]), "#334155"),
            "home_building_id": home_building_id,
            "home_point": home_point,
            "assigned_destination_id": None if assigned_destination_id in {"None", None} else str(assigned_destination_id),
            "assigned_destination_usage": str(row.get("assigned_destination_usage") or ""),
            "assigned_destination_point": assigned_destination_point,
            "escort_mode": str(row.get("escort_mode") or "none"),
            "school_access_status": str(row.get("school_access_status") or "not_applicable"),
            "school_distance_m": None if pd.isna(row.get("school_distance_m")) else float(row.get("school_distance_m")),
            "escort_guardian_id": None if pd.isna(row.get("escort_guardian_id")) else row.get("escort_guardian_id"),
            "escort_child_ids": [str(item) for item in row.get("escort_child_ids", [])],
            "escort_stop_hours": [int(hour) for hour in row.get("escort_stop_hours", [])],
            "timeline_states": [str(item) for item in row["timeline_states"]],
            "timeline_destinations": [
                None if item in {"None", None} else str(item)
                for item in row["timeline_destinations"]
            ],
            "timeline_labels": timeline_labels,
            "timeline_usages": timeline_usages,
            "timeline_points": timeline_points,
        }
        members_payload.append(member_payload)

        household_id = member_payload["household_id"] or member_payload["home_building_id"]
        household = households_index.setdefault(
            household_id,
            {
                "household_id": household_id,
                "home_building_id": home_building_id,
                "home_point": home_point,
                "member_ids": [],
                "roles": [],
                "escort_children_count": 0,
            },
        )
        household["member_ids"].append(member_payload["member_id"])
        household["roles"].append(member_payload["role"])
        if member_payload["role"] == "scolaire" and member_payload["escort_mode"] == "escort":
            household["escort_children_count"] += 1

        school_access_summary[member_payload["school_access_status"]] += 1

    households_payload = []
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

    bounds = gdf_model.to_crs("EPSG:4326").total_bounds
    return {
        "scenario_name": config.get("scenario", {}).get("name", "scenario"),
        "reference_hour": int(config.get("scenario", {}).get("reference_hour", 0)),
        "members": members_payload,
        "households": sorted(households_payload, key=lambda item: item["household_id"]),
        "role_counts": {str(key): int(value) for key, value in member_timelines["role"].value_counts().sort_index().to_dict().items()},
        "school_access_summary": {str(key): int(value) for key, value in sorted(school_access_summary.items())},
        "config_editor": {
            "fields": get_editable_config_fields(config),
            "yaml_patch": build_config_patch_yaml(config),
        },
        "map": {
            "bounds": [
                [float(bounds[1]), float(bounds[0])],
                [float(bounds[3]), float(bounds[2])],
            ],
        },
    }


def render_realtime_explorer_html() -> str:
    return """<!DOCTYPE html>
<html lang="fr">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Explorateur temps reel MOGEC</title>
  <style>
    :root {
      --card: rgba(255, 252, 246, 0.96);
      --line: #d8d0c0;
      --ink: #12252b;
      --muted: #5d6a70;
      --accent: #1f4e79;
      --shadow: 0 16px 40px rgba(18, 37, 43, 0.10);
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: "IBM Plex Sans", "Segoe UI", sans-serif;
      background:
        radial-gradient(circle at top left, rgba(31, 78, 121, 0.08), transparent 36%),
        linear-gradient(180deg, #f7f3e8 0%, #efe8da 100%);
      color: var(--ink);
    }
    .shell {
      display: grid;
      grid-template-columns: 430px 1fr;
      min-height: 100vh;
    }
    .sidebar {
      padding: 22px 18px;
      border-right: 1px solid rgba(18, 37, 43, 0.10);
      background: #f7f3e8;
      overflow-y: auto;
    }
    .map-wrap {
      position: relative;
      min-height: 100vh;
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
      border: 1px solid rgba(18,37,43,0.08);
      border-radius: 18px;
      box-shadow: var(--shadow);
      padding: 16px 18px;
      margin-bottom: 14px;
    }
    .hero h1 { margin: 0 0 8px; font-size: 1.95rem; line-height: 1.05; }
    .muted, .hero p { color: var(--muted); line-height: 1.45; margin: 0; }
    .grid-2 { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
    label { display: block; font-size: 0.82rem; color: var(--muted); margin-bottom: 6px; }
    select, input[type="range"], input[type="number"], button, textarea {
      width: 100%;
      border: 1px solid var(--line);
      border-radius: 12px;
      padding: 10px 12px;
      font: inherit;
      background: white;
    }
    textarea {
      min-height: 180px;
      resize: vertical;
      font: 0.9rem/1.45 "IBM Plex Mono", "SFMono-Regular", monospace;
      background: #fffdf8;
      contain: layout paint;
    }
    button { cursor: pointer; background: #f8fafc; }
    button.primary { background: var(--accent); color: white; border-color: var(--accent); }
    .toolbar { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin-top: 10px; }
    .hour-line { display: flex; align-items: center; gap: 12px; margin-top: 10px; }
    .hour-pill {
      min-width: 70px;
      text-align: center;
      border-radius: 999px;
      padding: 6px 10px;
      background: #f1f5f9;
      font-weight: 700;
    }
    .stats { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px; }
    .stat {
      border-radius: 14px;
      background: rgba(255,255,255,0.9);
      border: 1px solid rgba(18,37,43,0.08);
      padding: 12px;
    }
    .stat .label { color: var(--muted); font-size: 0.8rem; }
    .stat .value { font-size: 1.4rem; font-weight: 700; margin-top: 4px; }
    .list { display: grid; gap: 8px; }
    .list-item {
      border-radius: 12px;
      padding: 10px 12px;
      background: rgba(255,255,255,0.82);
      border: 1px solid rgba(18,37,43,0.08);
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
      width: 320px;
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
    @media (max-width: 1080px) {
      .shell { grid-template-columns: 1fr; }
      .map-wrap, #map { min-height: 70vh; height: 70vh; }
    }
  </style>
</head>
<body>
  <div class="shell">
    <aside class="sidebar">
      <section class="card hero">
        <h1>Explorateur temps reel</h1>
        <p>La preview reste autonome. Le fond de carte s'affiche meme si Leaflet ou les CDN externes sont indisponibles.</p>
      </section>

      <section class="card">
        <div class="grid-2">
          <div>
            <label for="basemapSelect">Fond de carte</label>
            <select id="basemapSelect">
              <option value="plan">Plan</option>
              <option value="satellite">Satellite</option>
            </select>
          </div>
          <div>
            <label for="roleSelect">Profil</label>
            <select id="roleSelect"></select>
          </div>
          <div>
            <label for="householdSelect">Foyer</label>
            <select id="householdSelect"></select>
          </div>
          <div>
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
        <div class="toolbar" style="grid-template-columns: 1fr;">
          <button id="resetMapViewButton">Recentrer la carte</button>
        </div>
      </section>

      <section class="card">
        <h3>Parametres live</h3>
        <div class="config-grid" id="configPanel"></div>
        <label for="configPatchTextarea" style="margin-top: 10px;">Patch YAML session</label>
        <textarea id="configPatchTextarea" spellcheck="false" autocomplete="off" autocorrect="off" autocapitalize="none"></textarea>
        <div class="toolbar">
          <button class="primary" id="applyConfigButton">Appliquer</button>
          <button id="resetConfigButton">Revenir au scenario initial</button>
        </div>
      </section>

      <section class="card">
        <div class="stats" id="statsPanel"></div>
      </section>

      <section class="card">
        <h3>Foyer courant</h3>
        <div class="list" id="householdPanel"></div>
      </section>

      <section class="card">
        <h3>Trajectoire individuelle</h3>
        <div class="list" id="memberPanel"></div>
      </section>
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
      configDraftYaml: '',
      playing: false,
      timer: null,
      mapView: { panX: 0, panY: 0, zoomFactor: 1, dragging: false, pointerId: null, lastX: 0, lastY: 0 },
    };

    const roleSelect = document.getElementById('roleSelect');
    const householdSelect = document.getElementById('householdSelect');
    const memberSelect = document.getElementById('memberSelect');
    const basemapSelect = document.getElementById('basemapSelect');
    const hourSlider = document.getElementById('hourSlider');
    const hourLabel = document.getElementById('hourLabel');
    const playButton = document.getElementById('playButton');
    const refreshButton = document.getElementById('refreshButton');
    const resetMapViewButton = document.getElementById('resetMapViewButton');
    const applyConfigButton = document.getElementById('applyConfigButton');
    const resetConfigButton = document.getElementById('resetConfigButton');
    const statsPanel = document.getElementById('statsPanel');
    const householdPanel = document.getElementById('householdPanel');
    const memberPanel = document.getElementById('memberPanel');
    const roleLegend = document.getElementById('roleLegend');
    const scenarioLabel = document.getElementById('scenarioLabel');
    const configPanel = document.getElementById('configPanel');
    const configPatchTextarea = document.getElementById('configPatchTextarea');
    const mapRoot = document.getElementById('map');
    const mapTiles = document.getElementById('mapTiles');
    const mapOverlay = document.getElementById('mapOverlay');
    const mapBadge = document.getElementById('mapBadge');

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

    function activityName(member, hour) {
      const label = member.timeline_states[hour];
      if (label === 'domicile') return 'Domicile';
      if (label === 'interne') return member.timeline_labels[hour];
      return 'Exterieur commune';
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

      scenarioLabel.textContent = `${state.data.scenario_name} · T0 = h${String(state.data.reference_hour).padStart(2, '0')}`;
      roleLegend.innerHTML = Object.keys(state.data.role_counts).map((role) => `
        <div style="margin-top: 8px;">
          <span class="swatch" style="background:${state.data.members.find((member) => member.role === role)?.role_color || '#334155'}"></span>
          ${roleName(role)} (${state.data.role_counts[role]})
        </div>
      `).join('');
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
        ['Population filtree', members.length],
        ['Au domicile', counts.domicile],
        ['En interne', counts.interne],
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
    }

    function renderConfigPanel() {
      const fields = state.data?.config_editor?.fields || [];
      configPanel.innerHTML = fields.map((field) => {
        if (field.type === 'boolean') {
          return `
            <div>
              <label>${field.label}</label>
              <div class="checkline">
                <input type="checkbox" data-config-path="${field.path}" ${field.value ? 'checked' : ''}>
                <span class="muted">${field.value ? 'active' : 'inactive'}</span>
              </div>
            </div>
          `;
        }
        if (field.type === 'select') {
          return `
            <div>
              <label for="cfg-${field.path}">${field.label}</label>
              <select id="cfg-${field.path}" data-config-path="${field.path}">
                ${field.options.map((option) => `<option value="${option}" ${option === field.value ? 'selected' : ''}>${option}</option>`).join('')}
              </select>
            </div>
          `;
        }
        return `
          <div>
            <label for="cfg-${field.path}">${field.label}</label>
            <input id="cfg-${field.path}" type="number" data-config-path="${field.path}" value="${field.value ?? ''}" min="${field.min ?? ''}" max="${field.max ?? ''}" step="${field.step ?? 'any'}">
          </div>
        `;
      }).join('');
      const yamlPatch = state.configDraftYaml || state.data?.config_editor?.yaml_patch || '';
      if (document.activeElement !== configPatchTextarea || configPatchTextarea.value === '') {
        configPatchTextarea.value = yamlPatch;
      }
    }

    function collectConfigUpdates() {
      const updates = {};
      const fields = state.data?.config_editor?.fields || [];
      fields.forEach((field) => {
        const element = configPanel.querySelector(`[data-config-path="${field.path}"]`);
        if (!element) return;
        if (field.type === 'boolean') updates[field.path] = element.checked;
        else if (field.type === 'integer') updates[field.path] = Number.parseInt(element.value, 10);
        else if (field.type === 'number') updates[field.path] = Number.parseFloat(element.value);
        else updates[field.path] = element.value;
      });
      return updates;
    }

    function renderHouseholdPanel() {
      const householdId = state.memberId !== 'all'
        ? state.data.members.find((member) => member.member_id === state.memberId)?.household_id || 'all'
        : state.householdId;
      if (!state.data || householdId === 'all') {
        householdPanel.innerHTML = '<div class="muted">Selectionne un foyer ou une personne pour afficher la dynamique familiale.</div>';
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
          <span class="badge">${household.has_children ? 'avec enfant(s)' : 'sans enfant'}</span>
          <span class="badge">${household.escort_children_count} escorte(s)</span>
        </div>
      ` + members.map((member) => `
        <div class="list-item">
          <strong>${member.member_id}</strong><br>
          <span class="badge">${roleName(member.role)}</span>
          <span class="badge">${activityName(member, state.hour)}</span>
          ${member.school_access_status !== 'not_applicable' ? `<span class="badge">ecole: ${member.school_access_status}</span>` : ''}
          ${member.school_distance_m !== null ? `<span class="badge">${Math.round(member.school_distance_m)} m</span>` : ''}
        </div>
      `).join('');
    }

    function renderMemberPanel() {
      if (!state.data || state.memberId === 'all') {
        memberPanel.innerHTML = '<div class="muted">Selectionne une personne pour afficher son pas de temps et son mode d acces.</div>';
        return;
      }
      const member = state.data.members.find((item) => item.member_id === state.memberId);
      if (!member) {
        memberPanel.innerHTML = '<div class="muted">Personne introuvable.</div>';
        return;
      }
      const hours = Array.from({ length: 24 }, (_, hour) => `
        <div class="list-item" style="${hour === state.hour ? 'border-color:#1f4e79;background:#eff6ff;' : ''}">
          <strong>h${String(hour).padStart(2, '0')}</strong> · ${activityName(member, hour)}
        </div>
      `).join('');
      memberPanel.innerHTML = `
        <div class="list-item">
          <strong>${member.member_id}</strong><br>
          <span class="badge">${roleName(member.role)}</span>
          <span class="badge">acces ecole: ${member.school_access_status}</span>
          ${member.escort_guardian_id ? `<span class="badge">parent: ${member.escort_guardian_id}</span>` : ''}
        </div>
      ` + hours;
    }

    function currentPoint(member) {
      return member.timeline_points[state.hour];
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
      mapBadge.textContent = 'Carte prete, deplace la vue a la souris ou zoome a la molette.';
    }

    function bindMapInteractions() {
      mapRoot.addEventListener('pointerdown', (event) => {
        if (event.button !== 0) return;
        state.mapView.dragging = true;
        state.mapView.pointerId = event.pointerId;
        state.mapView.lastX = event.clientX;
        state.mapView.lastY = event.clientY;
        mapRoot.classList.add('is-dragging');
        mapRoot.setPointerCapture(event.pointerId);
      });

      mapRoot.addEventListener('pointermove', (event) => {
        if (!state.mapView.dragging || state.mapView.pointerId !== event.pointerId) return;
        const dx = event.clientX - state.mapView.lastX;
        const dy = event.clientY - state.mapView.lastY;
        state.mapView.panX += dx;
        state.mapView.panY += dy;
        state.mapView.lastX = event.clientX;
        state.mapView.lastY = event.clientY;
        renderMap();
      });

      function stopDragging(event) {
        if (state.mapView.pointerId !== null && event.pointerId === state.mapView.pointerId) {
          state.mapView.dragging = false;
          state.mapView.pointerId = null;
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
        ? 'Fond satellite si les tuiles externes sont accessibles. Glisser = deplacement, molette = zoom.'
        : 'Fond plan si les tuiles externes sont accessibles. Glisser = deplacement, molette = zoom.';
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

      const members = filteredMembers();
      const household = state.householdId !== 'all'
        ? state.data.households.find((item) => item.household_id === state.householdId)
        : null;
      const homePoint = household ? pointToScreen(household.home_point, view) : null;

      members.forEach((member) => {
        if (state.memberId === member.member_id) {
          const path = dedupedPath(member.timeline_points).map((point) => pointToScreen(point, view)).filter(Boolean);
          if (path.length >= 2) {
            mapOverlay.appendChild(svgElement('polyline', {
              points: path.map((item) => `${item[0]},${item[1]}`).join(' '),
              fill: 'none',
              stroke: member.role_color,
              'stroke-width': 3,
              'stroke-opacity': 0.75,
            }));
          }
        }
      });

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
    }

    function updateHour(hour) {
      state.hour = Number(hour);
      hourSlider.value = state.hour;
      hourLabel.textContent = `h${String(state.hour).padStart(2, '0')}`;
      renderStats();
      renderHouseholdPanel();
      renderMemberPanel();
      renderMap();
    }

    function syncView() {
      populateControls();
      renderConfigPanel();
      updateHour(state.hour);
    }

    function bindEvents() {
      window.addEventListener('resize', () => renderMap());
      basemapSelect.addEventListener('change', () => renderMap());
      configPatchTextarea.addEventListener('input', () => {
        state.configDraftYaml = configPatchTextarea.value;
      });
      configPatchTextarea.addEventListener('change', () => {
        state.configDraftYaml = configPatchTextarea.value;
      });
      configPatchTextarea.addEventListener('blur', () => {
        state.configDraftYaml = configPatchTextarea.value;
      });
      resetMapViewButton.addEventListener('click', () => {
        resetMapView();
        renderMap();
      });
      roleSelect.addEventListener('change', () => {
        state.role = roleSelect.value;
        state.householdId = 'all';
        state.memberId = 'all';
        syncView();
      });
      householdSelect.addEventListener('change', () => {
        state.householdId = householdSelect.value;
        state.memberId = 'all';
        syncView();
      });
      memberSelect.addEventListener('change', () => {
        state.memberId = memberSelect.value;
        if (state.memberId !== 'all') {
          const member = state.data.members.find((item) => item.member_id === state.memberId);
          if (member) state.householdId = member.household_id || 'all';
        }
        syncView();
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
        refreshButton.textContent = 'Rechargement...';
        await loadData(true);
        refreshButton.disabled = false;
        refreshButton.textContent = 'Recharger le scenario';
      });

      applyConfigButton.addEventListener('click', async () => {
        applyConfigButton.disabled = true;
        applyConfigButton.textContent = 'Application...';
        const response = await fetch('/api/config', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            updates: collectConfigUpdates(),
            yaml_patch: configPatchTextarea.value,
          }),
        });
        state.data = await response.json();
        state.hour = state.data.reference_hour;
        state.configDraftYaml = state.data?.config_editor?.yaml_patch || '';
        resetMapView();
        syncView();
        applyConfigButton.disabled = false;
        applyConfigButton.textContent = 'Appliquer';
      });

      resetConfigButton.addEventListener('click', async () => {
        resetConfigButton.disabled = true;
        resetConfigButton.textContent = 'Reinitialisation...';
        const response = await fetch('/api/config', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ reset: true }),
        });
        state.data = await response.json();
        state.role = 'all';
        state.householdId = 'all';
        state.memberId = 'all';
        state.hour = state.data.reference_hour;
        state.configDraftYaml = state.data?.config_editor?.yaml_patch || '';
        resetMapView();
        syncView();
        resetConfigButton.disabled = false;
        resetConfigButton.textContent = 'Revenir au scenario initial';
      });
    }

    async function loadData(refresh = false) {
      const response = await fetch(`/api/state${refresh ? '?refresh=1' : ''}`);
      state.data = await response.json();
      state.hour = state.data.reference_hour;
      state.configDraftYaml = state.data?.config_editor?.yaml_patch || '';
      resetMapView();
      syncView();
    }

    async function bootstrap() {
      initMap();
      bindMapInteractions();
      bindEvents();
      await loadData(false);
    }

    bootstrap();
  </script>
</body>
</html>
"""


class _ExplorerState:
    def __init__(self, config_path: str | Path):
        self.config_path = Path(config_path)
        self._lock = threading.Lock()
        self._base_config = load_config(self.config_path)
        self._current_config = deepcopy(self._base_config)
        self._gdf: gpd.GeoDataFrame | None = None
        self._payload: dict[str, Any] | None = None

    def payload(self, refresh: bool = False) -> dict[str, Any]:
        with self._lock:
            if refresh or self._payload is None or self._gdf is None:
                self._gdf = run_pipeline(self._current_config)
                self._payload = build_realtime_explorer_payload(self._gdf, self._current_config)
            return self._payload

    def update_config(
        self,
        updates: dict[str, Any] | None = None,
        yaml_patch: str | None = None,
        reset: bool = False,
    ) -> dict[str, Any]:
        with self._lock:
            previous_config = deepcopy(self._current_config)
            if reset:
                self._current_config = deepcopy(self._base_config)
            if yaml_patch:
                self._current_config = apply_yaml_patch(self._current_config, yaml_patch)
            if updates:
                self._current_config = apply_config_updates(self._current_config, updates)

            rebuild_mode = _classify_rebuild_mode(
                _diff_config_paths(previous_config, self._current_config),
                has_cached_gdf=self._gdf is not None,
            )
            if rebuild_mode == "full":
                self._gdf = run_pipeline(self._current_config)
            elif rebuild_mode == "temporal_only":
                self._gdf = generer_matrice_horaire(self._gdf, self._current_config)

            if self._gdf is None:
                self._gdf = run_pipeline(self._current_config)
            self._payload = build_realtime_explorer_payload(self._gdf, self._current_config)
            return self._payload


def _handler_factory(state: _ExplorerState):
    class ExplorerHandler(BaseHTTPRequestHandler):
        def _send_json(self, payload: dict[str, Any]) -> None:
            data = json.dumps(payload).encode("utf-8")
            self.send_response(200)
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
            if parsed.path == "/api/state":
                refresh = parse_qs(parsed.query).get("refresh", ["0"])[0] == "1"
                self._send_json(state.payload(refresh=refresh))
                return
            if parsed.path in {"/", "/index.html"}:
                self._send_html(render_realtime_explorer_html())
                return
            self.send_error(404, "Resource not found")

        def do_POST(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            if parsed.path != "/api/config":
                self.send_error(404, "Resource not found")
                return
            content_length = int(self.headers.get("Content-Length", "0"))
            raw_body = self.rfile.read(content_length) if content_length > 0 else b"{}"
            payload = json.loads(raw_body.decode("utf-8") or "{}")
            updates = payload.get("updates", {})
            yaml_patch = payload.get("yaml_patch", "")
            reset = bool(payload.get("reset", False))
            self._send_json(state.update_config(updates=updates, yaml_patch=yaml_patch, reset=reset))

        def log_message(self, format: str, *args) -> None:  # noqa: A003
            return

    return ExplorerHandler


def serve_realtime_explorer(config_path: str | Path, host: str = "127.0.0.1", port: int = 8765) -> ThreadingHTTPServer:
    state = _ExplorerState(config_path)
    return ThreadingHTTPServer((host, port), _handler_factory(state))
