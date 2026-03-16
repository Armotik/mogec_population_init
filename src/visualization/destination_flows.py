"""
Visualisation analytique des destinations du modele.

La figure produite est un tableau de bord de lecture territoriale combinant :
- des cartes de batiments pour localiser les flux et les poles d'arrivee ;
- des graphiques statistiques pour lire les types de destination ;
- des indicateurs synthetiques pour resumer la situation a T0.

Le module sert a documenter le comportement du modele, pas a presenter une
mobilite observee.
"""

from __future__ import annotations

import logging
from pathlib import Path

import geopandas as gpd
import matplotlib.pyplot as plt
import pandas as pd
import seaborn as sns
from matplotlib.lines import Line2D
from matplotlib.patches import Patch
from shapely.geometry import LineString

logger = logging.getLogger(__name__)


ROLE_COLORS = {
    "scolaire": "#2a6f97",
    "actif_local": "#dd6b20",
    "actif_navetteur": "#6b7280",
    "senior": "#3f8f5f",
}

BASE_BUILDING_FACE = "#f5f5f4"
BASE_BUILDING_EDGE = "#d6d3d1"
ORIGIN_EDGE = "#94a3b8"
PANEL_BACKGROUND = "#fcfcfb"


def _destination_assignments(df: gpd.GeoDataFrame) -> pd.DataFrame:
    """Reconstruit la table membre -> destination a partir des foyers."""
    building_by_id = df.set_index("building_id")
    rows: list[dict] = []

    for _, origin in df.iterrows():
        households = origin.get("households", [])
        if not households:
            continue

        origin_centroid = origin.geometry.centroid
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
                        "origin_geometry": origin_centroid,
                        "destination_geometry": destination.geometry.centroid,
                    }
                )

    return pd.DataFrame(rows)


def _aggregate_flow_lines(assignments: pd.DataFrame, crs: str) -> gpd.GeoDataFrame:
    """Agrege les flux origine -> destination pour limiter la surcharge visuelle."""
    if assignments.empty:
        return gpd.GeoDataFrame(columns=["flow_count", "role", "geometry"], geometry="geometry", crs=crs)

    aggregated = (
        assignments.groupby(
            ["origin_building_id", "destination_building_id", "destination_usage_1", "role"],
            as_index=False,
        )
        .agg(
            flow_count=("role", "size"),
            origin_geometry=("origin_geometry", "first"),
            destination_geometry=("destination_geometry", "first"),
        )
    )
    aggregated["geometry"] = aggregated.apply(
        lambda row: LineString([row["origin_geometry"], row["destination_geometry"]]),
        axis=1,
    )
    return gpd.GeoDataFrame(aggregated, geometry="geometry", crs=crs)


def _aggregate_destinations(assignments: pd.DataFrame, df: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Agrege les batiments destination et conserve leur emprise reelle."""
    if assignments.empty:
        return gpd.GeoDataFrame(
            columns=["destination_building_id", "incoming_agents", "destination_usage_1", "geometry"],
            geometry="geometry",
            crs=df.crs,
        )

    destination_counts = (
        assignments.groupby(["destination_building_id", "destination_usage_1"], as_index=False)
        .agg(incoming_agents=("role", "size"))
        .rename(columns={"destination_building_id": "building_id"})
    )

    role_breakdown = (
        assignments.groupby(["destination_building_id", "role"])
        .size()
        .unstack(fill_value=0)
        .reset_index()
        .rename(columns={"destination_building_id": "building_id"})
    )

    destination_buildings = df[["building_id", "usage_1", "geometry"]].merge(
        destination_counts,
        on="building_id",
        how="inner",
    )
    destination_buildings = destination_buildings.merge(role_breakdown, on="building_id", how="left")
    destination_buildings = destination_buildings.rename(
        columns={
            "building_id": "destination_building_id",
            "usage_1": "building_usage_1",
        }
    )
    return gpd.GeoDataFrame(destination_buildings, geometry="geometry", crs=df.crs)


def _collapse_destination_types(destination_buildings: gpd.GeoDataFrame, top_n: int) -> dict[str, str]:
    """Regroupe les types rares pour garder une lecture graphique stable."""
    counts = (
        destination_buildings.groupby("destination_usage_1", as_index=False)["incoming_agents"]
        .sum()
        .sort_values("incoming_agents", ascending=False)
    )
    top_types = set(counts.head(top_n)["destination_usage_1"].tolist())
    return {
        usage: usage if usage in top_types else "Autres destinations"
        for usage in destination_buildings["destination_usage_1"].unique()
    }


def _type_palette(ordered_types: list[str]) -> dict[str, tuple[float, float, float, float]]:
    palette = sns.color_palette("crest", n_colors=max(len(ordered_types), 3))
    return {usage: palette[index % len(palette)] for index, usage in enumerate(ordered_types)}


def _label_building(row: pd.Series, rank: int) -> str:
    usage = str(row.get("destination_usage_group", "Inconnu"))
    suffix = str(row.get("destination_building_id", ""))[-6:]
    return f"#{rank} {suffix} | {usage}"


def _plot_base_buildings(ax: plt.Axes, df: gpd.GeoDataFrame) -> None:
    df.plot(
        ax=ax,
        facecolor=BASE_BUILDING_FACE,
        edgecolor=BASE_BUILDING_EDGE,
        linewidth=0.20,
        alpha=1.0,
        zorder=1,
    )


def _annotate_top_destinations(
    ax: plt.Axes,
    destination_buildings: gpd.GeoDataFrame,
    annotation_count: int,
) -> None:
    top_destinations = destination_buildings.nlargest(annotation_count, "incoming_agents").copy()
    for rank, (_, row) in enumerate(top_destinations.iterrows(), start=1):
        centroid = row.geometry.centroid
        ax.text(
            centroid.x,
            centroid.y,
            str(rank),
            fontsize=8,
            fontweight="bold",
            ha="center",
            va="center",
            color="#111827",
            bbox={"boxstyle": "circle,pad=0.20", "facecolor": "white", "edgecolor": "#111827", "alpha": 0.92},
            zorder=8,
        )


def _safe_pop_t0(df: gpd.GeoDataFrame) -> int:
    if "pop_t0" in df.columns:
        return int(pd.Series(df["pop_t0"]).fillna(0).sum())
    if "households" not in df.columns:
        return 0

    total = 0
    for households in df["households"]:
        if not households:
            continue
        for household in households:
            total += len(household.get("members", []))
    return total


def _metric_cards(ax: plt.Axes, metrics: list[tuple[str, str, str]]) -> None:
    ax.axis("off")
    x_positions = [0.02, 0.27, 0.52, 0.77]

    for (title, value, subtitle), x in zip(metrics, x_positions, strict=False):
        ax.text(
            x,
            0.72,
            title,
            fontsize=10,
            fontweight="bold",
            color="#475569",
            transform=ax.transAxes,
        )
        ax.text(
            x,
            0.34,
            value,
            fontsize=22,
            fontweight="bold",
            color="#0f172a",
            transform=ax.transAxes,
        )
        ax.text(
            x,
            0.10,
            subtitle,
            fontsize=9,
            color="#64748b",
            transform=ax.transAxes,
        )


def plot_destination_flows(df: gpd.GeoDataFrame, output_path: str, config: dict) -> Path:
    """
    Produit un tableau de bord de lecture des destinations modelisees.

    Parameters
    ----------
    df:
        GeoDataFrame complet du pipeline, avant export, contenant `households`.
    output_path:
        Fichier PNG de destination.
    config:
        Configuration projet, utilisee pour les seuils de visualisation.
    """
    logger.info("Generation de la visualisation des flux de destination...")
    sns.set_theme(style="whitegrid", context="talk", font_scale=0.90)

    visu_cfg = config.get("visualization", {}).get("destination_flows", {})
    min_flow_count = int(visu_cfg.get("min_flow_count", 2))
    top_destination_types = int(visu_cfg.get("top_destination_types", 8))
    top_destination_buildings = int(visu_cfg.get("top_destination_buildings", 12))
    annotate_top_destinations = int(visu_cfg.get("annotate_top_destinations", 6))
    flow_width_scale = float(visu_cfg.get("flow_width_scale", 0.30))
    figure_size = tuple(visu_cfg.get("figure_size", [24, 16]))

    assignments = _destination_assignments(df)
    if assignments.empty:
        raise ValueError("Aucune destination interne exploitable n'a ete trouvee pour la visualisation.")

    flow_lines = _aggregate_flow_lines(assignments, str(df.crs))
    flow_lines = flow_lines[flow_lines["flow_count"] >= min_flow_count].copy()

    destination_buildings = _aggregate_destinations(assignments, df)
    usage_groups = _collapse_destination_types(destination_buildings, top_destination_types)
    destination_buildings["destination_usage_group"] = destination_buildings["destination_usage_1"].map(usage_groups)
    flow_lines["destination_usage_group"] = flow_lines["destination_usage_1"].map(usage_groups)

    ordered_types = (
        destination_buildings.groupby("destination_usage_group")["incoming_agents"]
        .sum()
        .sort_values(ascending=False)
        .index
        .tolist()
    )
    type_colors = _type_palette(ordered_types)

    type_counts = (
        destination_buildings.groupby("destination_usage_group", as_index=False)["incoming_agents"]
        .sum()
        .sort_values("incoming_agents", ascending=False)
    )

    role_destination = (
        assignments.assign(destination_usage_group=assignments["destination_usage_1"].map(usage_groups))
        .groupby(["destination_usage_group", "role"], as_index=False)
        .size()
        .rename(columns={"size": "agent_count"})
    )
    role_heatmap = (
        role_destination.pivot(index="destination_usage_group", columns="role", values="agent_count")
        .fillna(0)
    )
    if not role_heatmap.empty:
        role_heatmap = role_heatmap.loc[type_counts["destination_usage_group"].tolist()]
        ordered_roles = [role for role in ROLE_COLORS if role in role_heatmap.columns]
        role_heatmap = role_heatmap[ordered_roles]

    top_buildings = destination_buildings.nlargest(top_destination_buildings, "incoming_agents").copy()
    top_buildings["building_label"] = [
        _label_building(row, rank)
        for rank, (_, row) in enumerate(top_buildings.iterrows(), start=1)
    ]

    origin_buildings = df[df["building_id"].isin(assignments["origin_building_id"].unique())].copy()

    pop_t0 = _safe_pop_t0(df)
    total_internal_agents = int(len(assignments))
    n_origins = int(assignments["origin_building_id"].nunique())
    n_destinations = int(destination_buildings["destination_building_id"].nunique())
    avg_agents_per_destination = destination_buildings["incoming_agents"].mean()
    internal_share = (total_internal_agents / pop_t0 * 100.0) if pop_t0 else 0.0

    metrics = [
        ("Population a T0", f"{pop_t0:,}".replace(",", " "), "Total des agents dans le scenario"),
        ("Flux internes", f"{total_internal_agents:,}".replace(",", " "), "Affectations vers un batiment interne"),
        ("Batiments destination", f"{n_destinations:,}".replace(",", " "), "Recevant au moins un agent"),
        ("Part mobile interne", f"{internal_share:.1f}%", f"Moyenne {avg_agents_per_destination:.1f} agents/destination"),
    ]

    fig = plt.figure(figsize=figure_size, constrained_layout=True, facecolor="#f8fafc")
    grid = fig.add_gridspec(
        3,
        3,
        height_ratios=[0.34, 1.25, 1.0],
        width_ratios=[1.35, 1.05, 1.0],
    )

    ax_metrics = fig.add_subplot(grid[0, :])
    ax_map = fig.add_subplot(grid[1, :2])
    ax_hotspots = fig.add_subplot(grid[1, 2])
    ax_types = fig.add_subplot(grid[2, 0])
    ax_heatmap = fig.add_subplot(grid[2, 1])
    ax_top = fig.add_subplot(grid[2, 2])

    for ax in [ax_map, ax_hotspots, ax_types, ax_heatmap, ax_top]:
        ax.set_facecolor(PANEL_BACKGROUND)

    _metric_cards(ax_metrics, metrics)

    _plot_base_buildings(ax_map, df)
    if not origin_buildings.empty:
        origin_buildings.plot(
            ax=ax_map,
            facecolor="none",
            edgecolor=ORIGIN_EDGE,
            linewidth=0.30,
            alpha=0.28,
            zorder=2,
        )
    for role, color in ROLE_COLORS.items():
        role_lines = flow_lines[flow_lines["role"] == role]
        if role_lines.empty:
            continue
        role_lines.plot(
            ax=ax_map,
            color=color,
            linewidth=0.6 + role_lines["flow_count"] * flow_width_scale,
            alpha=0.24,
            zorder=3,
        )
    for usage_group, subset in destination_buildings.groupby("destination_usage_group"):
        subset.plot(
            ax=ax_map,
            facecolor=type_colors[usage_group],
            edgecolor="#0f172a",
            linewidth=0.45,
            alpha=0.80,
            zorder=5,
        )
    _annotate_top_destinations(ax_map, destination_buildings, annotate_top_destinations)
    ax_map.set_title("Carte des flux et des batiments destination", fontsize=15, fontweight="bold")
    ax_map.axis("off")

    _plot_base_buildings(ax_hotspots, df)
    destination_buildings.plot(
        ax=ax_hotspots,
        column="incoming_agents",
        cmap="YlOrBr",
        edgecolor="#7c2d12",
        linewidth=0.40,
        alpha=0.92,
        legend=True,
        legend_kwds={"label": "Agents recus par batiment", "shrink": 0.72},
        zorder=4,
    )
    _annotate_top_destinations(ax_hotspots, destination_buildings, annotate_top_destinations)
    ax_hotspots.set_title("Intensite des destinations", fontsize=14, fontweight="bold")
    ax_hotspots.axis("off")

    if not type_counts.empty:
        sns.barplot(
            data=type_counts,
            x="incoming_agents",
            y="destination_usage_group",
            hue="destination_usage_group",
            palette=type_colors,
            dodge=False,
            legend=False,
            ax=ax_types,
        )
        for patch, value in zip(ax_types.patches, type_counts["incoming_agents"], strict=False):
            ax_types.text(value + 0.4, patch.get_y() + patch.get_height() / 2, str(int(value)), va="center", fontsize=9)
    ax_types.set_title("Agents diriges par type de batiment", fontsize=14, fontweight="bold")
    ax_types.set_xlabel("Nombre d'agents")
    ax_types.set_ylabel("")
    sns.despine(ax=ax_types, left=False, bottom=False)

    if not role_heatmap.empty:
        sns.heatmap(
            role_heatmap,
            cmap="mako",
            linewidths=0.5,
            linecolor="#e2e8f0",
            annot=True,
            fmt=".0f",
            cbar_kws={"label": "Agents"},
            ax=ax_heatmap,
        )
    ax_heatmap.set_title("Roles x types de destination", fontsize=14, fontweight="bold")
    ax_heatmap.set_xlabel("Role")
    ax_heatmap.set_ylabel("")

    if not top_buildings.empty:
        top_palette = [type_colors[usage] for usage in top_buildings["destination_usage_group"]]
        sns.barplot(
            data=top_buildings,
            x="incoming_agents",
            y="building_label",
            hue="building_label",
            palette=top_palette,
            dodge=False,
            legend=False,
            ax=ax_top,
        )
        for patch, value in zip(ax_top.patches, top_buildings["incoming_agents"], strict=False):
            ax_top.text(value + 0.3, patch.get_y() + patch.get_height() / 2, str(int(value)), va="center", fontsize=8)
    ax_top.set_title("Principaux batiments d'arrivee", fontsize=14, fontweight="bold")
    ax_top.set_xlabel("Agents recus")
    ax_top.set_ylabel("")
    sns.despine(ax=ax_top, left=False, bottom=False)

    role_legend = [
        Line2D([0], [0], color=color, lw=3.0, label=role)
        for role, color in ROLE_COLORS.items()
        if role in assignments["role"].unique()
    ]
    type_legend = [
        Patch(facecolor=type_colors[usage], edgecolor="#0f172a", label=usage)
        for usage in ordered_types[: min(len(ordered_types), 8)]
    ]
    if role_legend:
        fig.legend(
            handles=role_legend,
            title="Flux par role",
            loc="lower left",
            bbox_to_anchor=(0.012, 0.045),
            ncol=max(1, len(role_legend)),
            frameon=True,
            fontsize=9,
            title_fontsize=10,
        )
    if type_legend:
        fig.legend(
            handles=type_legend,
            title="Types destination",
            loc="lower right",
            bbox_to_anchor=(0.988, 0.045),
            ncol=min(4, len(type_legend)),
            frameon=True,
            fontsize=9,
            title_fontsize=10,
        )

    fig.suptitle("Batz-sur-Mer : tableau de bord des destinations modelisees", fontsize=20, fontweight="bold", y=0.995)
    fig.text(
        0.012,
        0.012,
        (
            f"Batiments origine impliques : {n_origins} | "
            f"Seuil de flux affiche : >= {min_flow_count} | "
            "Les numeros sur cartes correspondent au classement des principaux batiments d'arrivee."
        ),
        fontsize=10,
        color="#475569",
    )

    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output, dpi=260, bbox_inches="tight", facecolor=fig.get_facecolor())
    plt.close(fig)
    logger.info("Visualisation des flux sauvegardee : %s", output)
    return output
