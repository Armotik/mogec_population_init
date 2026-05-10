#!/usr/bin/env python3
"""
Generate final-presentation evidence assets for the Xynthia scenario only.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import geopandas as gpd
import matplotlib.colors as mcolors
import matplotlib.pyplot as plt
import pandas as pd
import seaborn as sns

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.core.proxy_validation import evaluate_temporal_proxies
from src.io.loaders import load_study_area_boundary
from src.pipeline import load_config, run_pipeline
from src.visualization.destination_flows import _destination_assignments
from src.visualization.validation import (
    external_proxy_validation,
    hourly_population_profile,
    role_targets_vs_realized,
)


DEFAULT_CONFIG = "config/scenarios/xynthia_winter_night.yaml"
DEFAULT_OUTPUT_DIR = "data/04_visualization/final_presentation/xynthia"


def _fmt_int(value: float | int) -> str:
    return f"{int(round(float(value))):,}".replace(",", " ")


def _fmt_pct(value: float) -> str:
    return f"{float(value):.1f} %"


def _hour_label(hour: int) -> str:
    return f"h{int(hour):02d}"


def _t0_column(gdf: gpd.GeoDataFrame, config: dict) -> tuple[str, int]:
    reference_hour = int(config.get("scenario", {}).get("reference_hour", 0))
    column = f"pop_h{reference_hour}"
    if column not in gdf.columns:
        column = "pop_t0"
    return column, reference_hour


def _scenario_name(config: dict) -> str:
    return str(config.get("scenario", {}).get("name", "scenario"))


def _check_xynthia_only(config: dict) -> None:
    scenario_name = _scenario_name(config).lower()
    if "xynthia" not in scenario_name:
        raise ValueError(f"Scenario non autorise pour cette generation: {scenario_name}")


def _write_csv(df: pd.DataFrame, output_dir: Path, filename: str) -> Path:
    path = output_dir / filename
    df.to_csv(path, index=False)
    return path


def _save_heatmap(gdf: gpd.GeoDataFrame, config: dict, output_dir: Path) -> tuple[Path, pd.DataFrame]:
    pop_col, reference_hour = _t0_column(gdf, config)
    plot_gdf = gdf.copy()
    plot_gdf[pop_col] = plot_gdf[pop_col].fillna(0)
    occupied = plot_gdf[plot_gdf[pop_col] > 0].copy()
    occupied["density_agents_1000m2"] = occupied[pop_col] / occupied.geometry.area.clip(lower=1.0) * 1000.0

    total_agents = int(plot_gdf["pop_t0"].fillna(0).sum())
    occupied_buildings = int((plot_gdf["pop_t0"].fillna(0) > 0).sum())
    reference_population = int(plot_gdf[pop_col].sum())
    boundary = load_study_area_boundary(config, strict=True)
    total_area_km2 = float(boundary.geometry.area.sum() / 1_000_000.0)
    commune_density = total_agents / total_area_km2 if total_area_km2 > 0 else 0.0

    metrics = pd.DataFrame(
        [
            {"metric": "scenario", "value": _scenario_name(config)},
            {"metric": "t0_reference_hour", "value": _hour_label(reference_hour)},
            {"metric": "agents_t0", "value": total_agents},
            {"metric": "occupied_buildings_t0", "value": occupied_buildings},
            {"metric": "population_at_reference_hour", "value": reference_population},
            {"metric": "commune_area_km2", "value": round(total_area_km2, 3)},
            {"metric": "mean_density_agents_per_km2_commune", "value": round(commune_density, 1)},
        ]
    )

    fig, ax = plt.subplots(figsize=(16, 9), facecolor="white")
    ax.set_facecolor("#f8fafc")
    plot_gdf.plot(ax=ax, facecolor="#e7e5e4", edgecolor="#ffffff", linewidth=0.12, alpha=0.75)
    boundary.boundary.plot(ax=ax, color="#334155", linewidth=0.8, alpha=0.80)

    if not occupied.empty:
        vmin = max(float(occupied["density_agents_1000m2"].quantile(0.05)), 0.1)
        vmax = max(float(occupied["density_agents_1000m2"].quantile(0.98)), vmin * 1.5)
        occupied.plot(
            ax=ax,
            column="density_agents_1000m2",
            cmap="YlOrRd",
            norm=mcolors.LogNorm(vmin=vmin, vmax=vmax),
            edgecolor="#7f1d1d",
            linewidth=0.12,
            alpha=0.95,
            legend=True,
            legend_kwds={
                "label": f"Densite batimentaire a T0 ({_hour_label(reference_hour)}) - agents / 1000 m2",
                "shrink": 0.72,
            },
        )

    ax.text(
        0.02,
        0.04,
        (
            f"T0 = {_hour_label(reference_hour)} | "
            f"{_fmt_int(total_agents)} agents | "
            f"{_fmt_int(occupied_buildings)} batiments occupes"
        ),
        transform=ax.transAxes,
        fontsize=13,
        color="#0f172a",
        bbox={"boxstyle": "round,pad=0.45", "facecolor": "white", "edgecolor": "#cbd5e1", "alpha": 0.96},
    )
    ax.set_title("Result 1 - Building-scale presence at T0", fontsize=20, fontweight="bold", pad=12)
    ax.axis("off")
    path = output_dir / "slide_1_t0_density_heatmap.png"
    fig.savefig(path, dpi=240, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return path, metrics


def _destination_usage(assignments: pd.DataFrame) -> pd.DataFrame:
    if assignments.empty:
        return pd.DataFrame(columns=["destination_usage_1", "internal_assignments", "destination_buildings"])
    return (
        assignments.groupby("destination_usage_1", as_index=False)
        .agg(
            internal_assignments=("role", "size"),
            destination_buildings=("destination_building_id", "nunique"),
        )
        .sort_values("internal_assignments", ascending=False)
    )


def _save_hourly_destinations(gdf: gpd.GeoDataFrame, config: dict, output_dir: Path) -> tuple[Path, pd.DataFrame, pd.DataFrame]:
    hourly = hourly_population_profile(gdf)
    assignments = _destination_assignments(gdf)
    usage = _destination_usage(assignments)

    total_agents = int(gdf["pop_t0"].fillna(0).sum())
    internal_assignments = int(len(assignments))
    destination_buildings = int(assignments["destination_building_id"].nunique()) if not assignments.empty else 0
    internal_mobility_rate = internal_assignments / total_agents * 100.0 if total_agents else 0.0
    reference_hour = int(config.get("scenario", {}).get("reference_hour", 0))

    metrics = pd.DataFrame(
        [
            {"metric": "agents_t0", "value": total_agents},
            {"metric": "internal_assignments", "value": internal_assignments},
            {"metric": "destination_buildings", "value": destination_buildings},
            {"metric": "internal_mobility_rate_pct", "value": round(internal_mobility_rate, 2)},
            {"metric": "hourly_min_population", "value": int(hourly["population"].min())},
            {"metric": "hourly_max_population", "value": int(hourly["population"].max())},
            {"metric": "hourly_amplitude", "value": int(hourly["population"].max() - hourly["population"].min())},
        ]
    )

    fig, axes = plt.subplots(
        1,
        2,
        figsize=(16, 9),
        gridspec_kw={"width_ratios": [1.25, 1.0]},
        facecolor="white",
    )
    ax_curve, ax_bar = axes

    sns.lineplot(data=hourly, x="hour", y="population", marker="o", color="#1f4e79", linewidth=2.8, ax=ax_curve)
    ax_curve.fill_between(hourly["hour"], hourly["population"], color="#9ecae1", alpha=0.30)
    ax_curve.axvline(reference_hour, color="#111827", linestyle="--", linewidth=1.4)
    ax_curve.text(
        reference_hour + 0.25,
        float(hourly["population"].max()),
        f"T0 {_hour_label(reference_hour)}",
        color="#111827",
        fontsize=11,
        va="top",
        fontweight="bold",
    )
    ax_curve.set_title("Hourly presence curve", fontsize=16, fontweight="bold")
    ax_curve.set_xlabel("Heure")
    ax_curve.set_ylabel("Agents presents")
    ax_curve.set_xticks(range(0, 24, 2))
    ax_curve.grid(True, alpha=0.28)

    top_usage = usage.head(10).sort_values("internal_assignments", ascending=True)
    sns.barplot(
        data=top_usage,
        x="internal_assignments",
        y="destination_usage_1",
        hue="destination_usage_1",
        palette="viridis",
        legend=False,
        ax=ax_bar,
    )
    for patch, value in zip(ax_bar.patches, top_usage["internal_assignments"], strict=False):
        ax_bar.text(value + max(1, usage["internal_assignments"].max() * 0.01), patch.get_y() + patch.get_height() / 2, _fmt_int(value), va="center", fontsize=10)
    ax_bar.set_title("Internal destinations by usage", fontsize=16, fontweight="bold")
    ax_bar.set_xlabel("Assignements internes")
    ax_bar.set_ylabel("")
    ax_bar.grid(axis="x", alpha=0.25)

    fig.suptitle("Result 2 - Hourly dynamics and internal destinations", fontsize=20, fontweight="bold", y=0.98)
    fig.text(
        0.5,
        0.025,
        (
            f"{_fmt_int(internal_assignments)} assignements internes | "
            f"{_fmt_int(destination_buildings)} batiments destination | "
            f"taux de mobilite interne {_fmt_pct(internal_mobility_rate)}"
        ),
        ha="center",
        fontsize=13,
        color="#0f172a",
        bbox={"boxstyle": "round,pad=0.45", "facecolor": "#f8fafc", "edgecolor": "#cbd5e1"},
    )
    fig.tight_layout(rect=(0.02, 0.06, 0.98, 0.94))
    path = output_dir / "slide_2_hourly_presence_and_destinations.png"
    fig.savefig(path, dpi=240, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return path, metrics, usage


def _save_demographic_table(gdf: gpd.GeoDataFrame, config: dict, output_dir: Path) -> tuple[Path, pd.DataFrame]:
    roles = role_targets_vs_realized(gdf, config).copy()
    roles["target_share_pct"] = roles["target_share"] * 100.0
    roles["realized_share_pct"] = roles["realized_share"] * 100.0
    table = roles[
        [
            "role",
            "target_count",
            "realized_count",
            "gap_count",
            "target_share_pct",
            "realized_share_pct",
            "gap_share_pp",
        ]
    ].copy()

    display = table.copy()
    display["target_count"] = display["target_count"].map(_fmt_int)
    display["realized_count"] = display["realized_count"].map(_fmt_int)
    display["gap_count"] = display["gap_count"].map(lambda value: f"{int(value):+d}")
    display["target_share_pct"] = display["target_share_pct"].map(lambda value: f"{value:.1f} %")
    display["realized_share_pct"] = display["realized_share_pct"].map(lambda value: f"{value:.1f} %")
    display["gap_share_pp"] = display["gap_share_pp"].map(lambda value: f"{value:+.1f} pp")
    display = display.rename(
        columns={
            "role": "Role",
            "target_count": "Target",
            "realized_count": "Achieved",
            "gap_count": "Gap",
            "target_share_pct": "Target %",
            "realized_share_pct": "Achieved %",
            "gap_share_pp": "Gap pp",
        }
    )

    fig, ax = plt.subplots(figsize=(16, 9), facecolor="white")
    ax.axis("off")
    ax.set_title("Evaluation - Internal consistency and demographic targets", fontsize=20, fontweight="bold", pad=18)
    mpl_table = ax.table(
        cellText=display.values,
        colLabels=display.columns,
        cellLoc="center",
        colLoc="center",
        loc="center",
        colWidths=[0.18, 0.13, 0.13, 0.10, 0.13, 0.13, 0.10],
    )
    mpl_table.auto_set_font_size(False)
    mpl_table.set_fontsize(13)
    mpl_table.scale(1, 2.1)

    for (row, col), cell in mpl_table.get_celld().items():
        cell.set_edgecolor("#cbd5e1")
        if row == 0:
            cell.set_facecolor("#0f172a")
            cell.set_text_props(color="white", weight="bold")
        else:
            cell.set_facecolor("#f8fafc" if row % 2 == 0 else "white")

    max_gap = float(table["gap_share_pp"].abs().max()) if not table.empty else 0.0
    ax.text(
        0.5,
        0.12,
        f"Ecart maximal observe: {max_gap:.1f} point de pourcentage",
        transform=ax.transAxes,
        ha="center",
        fontsize=14,
        color="#0f172a",
        bbox={"boxstyle": "round,pad=0.45", "facecolor": "#f8fafc", "edgecolor": "#cbd5e1"},
    )
    path = output_dir / "slide_3_demographic_targets_table.png"
    fig.savefig(path, dpi=240, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return path, table


def _save_temporal_proxy(summary: pd.DataFrame, curves: pd.DataFrame, output_dir: Path) -> Path | None:
    if curves.empty:
        return None

    groups = list(curves.groupby("proxy_id", sort=False))
    fig, axes = plt.subplots(len(groups), 1, figsize=(16, max(5.0, 4.2 * len(groups))), squeeze=False, facecolor="white")
    axes_flat = axes.flatten()
    summary_lookup = summary.set_index("proxy_id") if not summary.empty else pd.DataFrame()

    for ax, (proxy_id, group) in zip(axes_flat, groups, strict=False):
        group = group.sort_values("hour")
        ax.plot(group["hour"], group["reference_compared"], label="Proxy/reference", color="#b91c1c", linewidth=2.6, marker="o")
        ax.plot(group["hour"], group["modeled_compared"], label="Modele Xynthia", color="#1d4ed8", linewidth=2.6, marker="o")
        ax.set_xlim(0, 23)
        ax.set_xticks(range(0, 24, 2))
        ax.set_ylabel("Valeur comparee")
        ax.grid(True, alpha=0.28)
        label = str(group["label"].iloc[0])
        subtitle = ""
        if proxy_id in summary_lookup.index:
            row = summary_lookup.loc[proxy_id]
            subtitle = f"status={row['status']} | corr={row['correlation']} | RMSE={row['rmse']} | pic_gap={row['peak_hour_gap']} h"
        ax.set_title(f"{label}\n{subtitle}", loc="left", fontsize=14, fontweight="bold")
        ax.legend(loc="upper right")

    axes_flat[-1].set_xlabel("Heure")
    fig.suptitle("Evaluation - Temporal proxy curve comparison", fontsize=20, fontweight="bold", y=0.99)
    fig.tight_layout(rect=(0.02, 0.02, 0.98, 0.94))
    path = output_dir / "slide_4_temporal_proxy_curves.png"
    fig.savefig(path, dpi=240, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return path


def _save_spatial_proxy(gdf: gpd.GeoDataFrame, config: dict, output_dir: Path) -> tuple[Path, pd.DataFrame]:
    proxies = external_proxy_validation(gdf, config).copy()
    plot_df = proxies.melt(
        id_vars=["proxy", "gap_value", "status", "interpretation"],
        value_vars=["reference_value", "modeled_value"],
        var_name="series",
        value_name="value",
    )
    plot_df["series"] = plot_df["series"].map({"reference_value": "Reference/proxy", "modeled_value": "Modele Xynthia"})

    fig, ax = plt.subplots(figsize=(16, 9), facecolor="white")
    sns.barplot(data=plot_df, x="value", y="proxy", hue="series", palette=["#b91c1c", "#1d4ed8"], ax=ax)
    for container in ax.containers:
        ax.bar_label(container, labels=[_fmt_int(v.get_width()) for v in container], padding=4, fontsize=10)
    ax.set_title("Evaluation - Spatial proxy comparison", fontsize=20, fontweight="bold", pad=12)
    ax.set_xlabel("Effectif")
    ax.set_ylabel("")
    ax.grid(axis="x", alpha=0.25)
    ax.legend(title="")

    status_text = " | ".join(f"{row.proxy}: {row.status} (gap {int(row.gap_value):+d})" for row in proxies.itertuples())
    ax.text(
        0.5,
        -0.16,
        status_text,
        transform=ax.transAxes,
        ha="center",
        fontsize=11,
        color="#0f172a",
        bbox={"boxstyle": "round,pad=0.45", "facecolor": "#f8fafc", "edgecolor": "#cbd5e1"},
    )
    fig.tight_layout(rect=(0.02, 0.08, 0.98, 0.95))
    path = output_dir / "slide_4_spatial_proxy_comparison.png"
    fig.savefig(path, dpi=240, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return path, proxies


def _write_text_evidence(
    output_dir: Path,
    config: dict,
    slide1_metrics: pd.DataFrame,
    slide2_metrics: pd.DataFrame,
    slide3_table: pd.DataFrame,
    temporal_summary: pd.DataFrame,
    spatial_proxy: pd.DataFrame,
) -> Path:
    metric1 = slide1_metrics.set_index("metric")["value"]
    metric2 = slide2_metrics.set_index("metric")["value"]
    max_demo_gap = float(slide3_table["gap_share_pp"].abs().max()) if not slide3_table.empty else 0.0

    temporal_lines = []
    for row in temporal_summary.itertuples():
        if bool(row.applicable):
            temporal_lines.append(
                f"- {row.proxy_id}: status {row.status}, correlation {row.correlation}, RMSE {row.rmse}, decalage du pic {row.peak_hour_gap} h."
            )
        else:
            temporal_lines.append(f"- {row.proxy_id}: non applicable au scenario Xynthia ({row.reason}), conserve comme information.")

    spatial_lines = [
        f"- {row.proxy}: reference {_fmt_int(row.reference_value)}, modele {_fmt_int(row.modeled_value)}, gap {int(row.gap_value):+d}, statut {row.status}."
        for row in spatial_proxy.itertuples()
    ]

    text = "\n".join(
        [
            f"# Preuves finales - scenario {_scenario_name(config)}",
            "",
            "## Slide 1 - Result 1: Building-scale presence at T0",
            f"- T0 correspond a {metric1['t0_reference_hour']}.",
            f"- Population a T0: {_fmt_int(metric1['agents_t0'])} agents.",
            f"- Batiments occupes a T0: {_fmt_int(metric1['occupied_buildings_t0'])}.",
            f"- Densite moyenne communale a T0: {float(metric1['mean_density_agents_per_km2_commune']):.1f} agents/km2.",
            "",
            "## Slide 2 - Result 2: Hourly dynamics and internal destinations",
            f"- Assignements internes: {_fmt_int(metric2['internal_assignments'])}.",
            f"- Batiments destination: {_fmt_int(metric2['destination_buildings'])}.",
            f"- Taux de mobilite interne: {_fmt_pct(float(metric2['internal_mobility_rate_pct']))}.",
            f"- Amplitude journaliere: {_fmt_int(metric2['hourly_amplitude'])} agents entre le minimum et le maximum horaires.",
            "",
            "## Slide 3 - Evaluation: Internal consistency and demographic targets",
            f"- Toutes les cibles demographiques sont realisees avec un ecart maximal de {max_demo_gap:.1f} point de pourcentage.",
            "- Le tableau `slide_3_demographic_targets.csv` donne target, achieved et gap pour chaque role.",
            "",
            "## Slide 4 - Evaluation: Indirect validation by proxies",
            "### Proxy temporel",
            *temporal_lines,
            "### Proxys spatiaux",
            *spatial_lines,
            "",
        ]
    )
    path = output_dir / "slide_text_evidence.md"
    path.write_text(text, encoding="utf-8")
    return path


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate final evidence assets for the Xynthia scenario only.")
    parser.add_argument("--config", default=DEFAULT_CONFIG, help="Path to the Xynthia scenario YAML.")
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR, help="Output directory for slide evidence.")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s - %(message)s")
    sns.set_theme(style="whitegrid", context="talk", font_scale=0.9)

    config_path = (ROOT_DIR / args.config).resolve()
    output_dir = (ROOT_DIR / args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    config = load_config(config_path)
    _check_xynthia_only(config)

    logging.info("Running pipeline for scenario %s", _scenario_name(config))
    gdf = run_pipeline(config)

    slide1_path, slide1_metrics = _save_heatmap(gdf, config, output_dir)
    slide2_path, slide2_metrics, usage = _save_hourly_destinations(gdf, config, output_dir)
    slide3_path, slide3_table = _save_demographic_table(gdf, config, output_dir)
    temporal_summary, temporal_curves = evaluate_temporal_proxies(gdf, config)
    temporal_path = _save_temporal_proxy(temporal_summary, temporal_curves, output_dir)
    spatial_path, spatial_proxy = _save_spatial_proxy(gdf, config, output_dir)
    text_path = _write_text_evidence(
        output_dir,
        config,
        slide1_metrics,
        slide2_metrics,
        slide3_table,
        temporal_summary,
        spatial_proxy,
    )

    generated = [
        slide1_path,
        slide2_path,
        slide3_path,
        spatial_path,
        text_path,
        _write_csv(slide1_metrics, output_dir, "slide_1_metrics.csv"),
        _write_csv(hourly_population_profile(gdf), output_dir, "slide_2_hourly_presence.csv"),
        _write_csv(usage, output_dir, "slide_2_destinations_by_usage.csv"),
        _write_csv(slide2_metrics, output_dir, "slide_2_metrics.csv"),
        _write_csv(slide3_table, output_dir, "slide_3_demographic_targets.csv"),
        _write_csv(temporal_summary, output_dir, "slide_4_temporal_proxy_summary.csv"),
        _write_csv(temporal_curves, output_dir, "slide_4_temporal_proxy_curves.csv"),
        _write_csv(spatial_proxy, output_dir, "slide_4_spatial_proxy_comparison.csv"),
    ]
    if temporal_path is not None:
        generated.insert(3, temporal_path)

    for path in generated:
        print(path.relative_to(ROOT_DIR))


if __name__ == "__main__":
    main()
