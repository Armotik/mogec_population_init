"""
Fonctions d'appui pour les notebooks de visualisation.

Le but est de fournir des tableaux deja structures pour l'exploration du
modele, sans imposer un tableau de bord unique. Les fonctions privilegient des
sorties simples : DataFrame de metriques, comptages par type de destination,
heatmap role x destination et classement des batiments d'arrivee.
"""

from __future__ import annotations

import geopandas as gpd
import pandas as pd


def build_destination_assignments(df: gpd.GeoDataFrame) -> pd.DataFrame:
    """
    Reconstruit la table membre -> destination a partir des foyers du modele.

    Parameters
    ----------
    df:
        GeoDataFrame issu du pipeline complet, contenant la colonne `households`.
    """
    building_by_id = df.set_index("building_id")
    rows: list[dict] = []

    for _, origin in df.iterrows():
        households = origin.get("households", [])
        if not households:
            continue

        for household in households:
            for member in household.get("members", []):
                destination_id = member.get("destination_id")
                if destination_id in {"DOMICILE", "EXTERIEUR", "None", None}:
                    continue
                if destination_id not in building_by_id.index:
                    continue

                destination = building_by_id.loc[destination_id]
                rows.append(
                    {
                        "origin_building_id": origin["building_id"],
                        "origin_usage_1": origin.get("usage_1", ""),
                        "destination_building_id": destination_id,
                        "destination_usage_1": destination.get("usage_1", ""),
                        "role": member.get("role", "unknown"),
                    }
                )

    return pd.DataFrame(rows)


def _collapse_destination_types(assignments: pd.DataFrame, top_n: int) -> dict[str, str]:
    counts = (
        assignments.groupby("destination_usage_1", as_index=False)
        .size()
        .rename(columns={"size": "agent_count"})
        .sort_values("agent_count", ascending=False)
    )
    top_types = set(counts.head(top_n)["destination_usage_1"].tolist())
    return {
        usage: usage if usage in top_types else "Autres destinations"
        for usage in assignments["destination_usage_1"].unique()
    }


def summarize_population_metrics(df: gpd.GeoDataFrame, assignments: pd.DataFrame) -> pd.DataFrame:
    """
    Produit quelques indicateurs globaux directement utiles en notebook.
    """
    hourly_cols = sorted(
        [col for col in df.columns if col.startswith("pop_h")],
        key=lambda name: int(name.replace("pop_h", "")),
    )
    pop_t0 = int(pd.Series(df.get("pop_t0", pd.Series(dtype=float))).fillna(0).sum()) if "pop_t0" in df.columns else 0
    inhabited_buildings = int((pd.Series(df.get("pop_t0", pd.Series(dtype=float))).fillna(0) > 0).sum()) if "pop_t0" in df.columns else 0
    destination_buildings = int(assignments["destination_building_id"].nunique()) if not assignments.empty else 0
    origin_buildings = int(assignments["origin_building_id"].nunique()) if not assignments.empty else 0
    internal_agents = int(len(assignments))
    avg_agents = float(internal_agents / destination_buildings) if destination_buildings else 0.0
    peak_hour = None
    peak_value = 0
    if hourly_cols:
        hourly_totals = df[hourly_cols].fillna(0).sum()
        peak_hour = hourly_totals.idxmax().replace("pop_h", "h")
        peak_value = int(hourly_totals.max())

    metrics = [
        ("population_t0", pop_t0),
        ("batiments_habites_t0", inhabited_buildings),
        ("flux_internes", internal_agents),
        ("batiments_origine", origin_buildings),
        ("batiments_destination", destination_buildings),
        ("agents_moyens_par_destination", round(avg_agents, 2)),
        ("heure_pic_global", peak_hour or "n/a"),
        ("population_pic_globale", peak_value),
    ]
    return pd.DataFrame(metrics, columns=["metric", "value"])


def hourly_population_curve(df: gpd.GeoDataFrame) -> pd.DataFrame:
    """
    Retourne la courbe horaire aggregatee de population sur 24h.
    """
    hourly_cols = sorted(
        [col for col in df.columns if col.startswith("pop_h")],
        key=lambda name: int(name.replace("pop_h", "")),
    )
    if not hourly_cols:
        return pd.DataFrame(columns=["hour", "population"])

    return pd.DataFrame(
        {
            "hour": [int(col.replace("pop_h", "")) for col in hourly_cols],
            "population": [int(df[col].fillna(0).sum()) for col in hourly_cols],
        }
    )


def destination_type_counts(assignments: pd.DataFrame, top_n: int = 8) -> pd.DataFrame:
    """
    Agrege les destinations par type de batiment, avec regroupement des classes rares.
    """
    if assignments.empty:
        return pd.DataFrame(columns=["destination_usage_group", "agent_count"])

    grouping = _collapse_destination_types(assignments, top_n=top_n)
    result = (
        assignments.assign(destination_usage_group=assignments["destination_usage_1"].map(grouping))
        .groupby("destination_usage_group", as_index=False)
        .size()
        .rename(columns={"size": "agent_count"})
        .sort_values("agent_count", ascending=False)
    )
    return result


def role_destination_heatmap(assignments: pd.DataFrame, top_n: int = 8) -> pd.DataFrame:
    """
    Produit la matrice role x type de destination pour une heatmap seaborn.
    """
    if assignments.empty:
        return pd.DataFrame()

    grouping = _collapse_destination_types(assignments, top_n=top_n)
    heatmap = (
        assignments.assign(destination_usage_group=assignments["destination_usage_1"].map(grouping))
        .groupby(["destination_usage_group", "role"])
        .size()
        .unstack(fill_value=0)
    )
    order = destination_type_counts(assignments, top_n=top_n)["destination_usage_group"].tolist()
    return heatmap.loc[order]


def top_destination_buildings(
    df: gpd.GeoDataFrame,
    assignments: pd.DataFrame,
    top_n: int = 10,
) -> gpd.GeoDataFrame:
    """
    Retourne les principaux batiments d'arrivee avec leur geometrie.
    """
    if assignments.empty:
        return gpd.GeoDataFrame(columns=["destination_building_id", "agent_count", "geometry"], geometry="geometry", crs=df.crs)

    counts = (
        assignments.groupby(["destination_building_id", "destination_usage_1"], as_index=False)
        .size()
        .rename(columns={"size": "agent_count", "destination_building_id": "building_id"})
        .sort_values("agent_count", ascending=False)
        .head(top_n)
    )
    result = df[["building_id", "geometry"]].merge(counts, on="building_id", how="inner")
    result = result.rename(columns={"building_id": "destination_building_id"})
    return gpd.GeoDataFrame(result, geometry="geometry", crs=df.crs)
