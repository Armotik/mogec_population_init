"""
Visualisations lisibles de la validation temporelle par proxys.
"""

from __future__ import annotations

from html import escape
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


PROXY_METADATA_COLUMNS = [
    "proxy_id",
    "label",
    "metric",
    "role",
    "state",
    "usage_any_of",
    "comparison_normalization",
    "formula",
    "source_name",
    "source_url",
    "source_url_secondary",
    "confidence",
    "temporal_scope",
    "spatial_scope",
    "reference_curve",
]


def _proxy_entries(config: dict) -> list[dict]:
    return [proxy for proxy in config.get("proxy_validation", {}).get("temporal_proxies", []) if proxy.get("enabled", True)]


def proxy_metadata_table(config: dict) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for proxy in _proxy_entries(config):
        evidence = proxy.get("evidence", {})
        reference_curve = proxy.get("reference_curve", [])
        rows.append(
            {
                "proxy_id": str(proxy.get("proxy_id", "")),
                "label": str(proxy.get("label", proxy.get("proxy_id", ""))),
                "metric": str(proxy.get("metric", "")),
                "role": str(proxy.get("role", "")),
                "state": str(proxy.get("state", "")),
                "usage_any_of": ", ".join(str(item) for item in proxy.get("usage_any_of", [])),
                "comparison_normalization": str(proxy.get("comparison_normalization", "max")),
                "formula": str(evidence.get("formula", "")),
                "source_name": str(evidence.get("source_name", "")),
                "source_url": str(evidence.get("source_url", "")),
                "source_url_secondary": str(evidence.get("source_url_secondary", "")),
                "confidence": str(evidence.get("confidence", "")),
                "temporal_scope": str(evidence.get("temporal_scope", "")),
                "spatial_scope": str(evidence.get("spatial_scope", "")),
                "reference_curve": " | ".join(f"h{hour}:{float(value):.2f}" for hour, value in enumerate(reference_curve)),
            }
        )
    return pd.DataFrame(rows, columns=PROXY_METADATA_COLUMNS)


def _summary_row_lookup(summary_df: pd.DataFrame) -> dict[tuple[str, str], pd.Series]:
    lookup: dict[tuple[str, str], pd.Series] = {}
    if summary_df.empty:
        return lookup
    for _, row in summary_df.iterrows():
        lookup[(str(row["scenario_name"]), str(row["proxy_id"]))] = row
    return lookup


def save_proxy_validation_figure(
    summary_df: pd.DataFrame,
    curves_df: pd.DataFrame,
    output_path: str | Path,
) -> Path:
    output_path = Path(output_path)
    if curves_df.empty:
        raise ValueError("Aucune courbe proxy a tracer.")

    summary_lookup = _summary_row_lookup(summary_df)
    grouped_items = list(curves_df.groupby(["scenario_name", "proxy_id"], sort=False))
    figure_height = max(3.5 * len(grouped_items), 4.0)
    fig, axes = plt.subplots(len(grouped_items), 1, figsize=(12, figure_height), squeeze=False)
    axes_flat = axes.flatten()

    for axis, ((scenario_name, proxy_id), group) in zip(axes_flat, grouped_items):
        group = group.sort_values("hour")
        summary_row = summary_lookup.get((str(scenario_name), str(proxy_id)))

        axis.plot(group["hour"], group["reference_compared"], label="Reference comparee", color="#b91c1c", linewidth=2.2)
        axis.plot(group["hour"], group["modeled_compared"], label="Modele compare", color="#1d4ed8", linewidth=2.2)
        axis.scatter(group["hour"], group["reference_compared"], color="#b91c1c", s=18)
        axis.scatter(group["hour"], group["modeled_compared"], color="#1d4ed8", s=18)
        axis.set_xlim(0, 23)
        axis.set_xticks(range(0, 24, 2))
        axis.set_ylabel("Valeur comparee")
        axis.grid(True, alpha=0.25)

        title = f"{scenario_name} | {proxy_id}"
        subtitle = ""
        if summary_row is not None:
            subtitle = (
                f"status={summary_row['status']} | corr={summary_row['correlation']} | "
                f"rmse={summary_row['rmse']} | pic_gap={summary_row['peak_hour_gap']}h | "
                f"norm={summary_row['comparison_normalization']}"
            )
        axis.set_title(title if not subtitle else f"{title}\n{subtitle}", loc="left", fontsize=11, fontweight="bold")
        axis.legend(loc="upper right")

    axes_flat[-1].set_xlabel("Heure")
    fig.tight_layout()
    fig.savefig(output_path, dpi=180, bbox_inches="tight")
    plt.close(fig)
    return output_path


def _html_table(df: pd.DataFrame) -> str:
    if df.empty:
        return "<p>Aucune donnee disponible.</p>"
    return df.to_html(index=False, escape=True, classes="report-table")


def _proxy_cards(metadata_df: pd.DataFrame) -> str:
    if metadata_df.empty:
        return "<p>Aucun proxy configure.</p>"

    cards: list[str] = []
    for _, row in metadata_df.iterrows():
        cards.append(
            "\n".join(
                [
                    '<article class="proxy-card">',
                    f"<h3>{escape(str(row['label']))}</h3>",
                    f"<p><strong>ID:</strong> {escape(str(row['proxy_id']))}</p>",
                    f"<p><strong>Metrique:</strong> {escape(str(row['metric']))}</p>",
                    f"<p><strong>Role:</strong> {escape(str(row['role'])) or 'n/a'}</p>",
                    f"<p><strong>Etat:</strong> {escape(str(row['state'])) or 'n/a'}</p>",
                    f"<p><strong>Usage bati:</strong> {escape(str(row['usage_any_of'])) or 'n/a'}</p>",
                    f"<p><strong>Normalisation:</strong> {escape(str(row['comparison_normalization']))}</p>",
                    f"<p><strong>Formule:</strong> {escape(str(row['formula']))}</p>",
                    f"<p><strong>Source:</strong> {escape(str(row['source_name']))}</p>",
                    f"<p><strong>URL principale:</strong> <a href=\"{escape(str(row['source_url']))}\">{escape(str(row['source_url']))}</a></p>",
                    f"<p><strong>URL secondaire:</strong> {escape(str(row['source_url_secondary'])) or 'n/a'}</p>",
                    f"<p><strong>Confiance:</strong> {escape(str(row['confidence']))}</p>",
                    f"<p><strong>Portee temporelle:</strong> {escape(str(row['temporal_scope']))}</p>",
                    f"<p><strong>Portee spatiale:</strong> {escape(str(row['spatial_scope']))}</p>",
                    f"<p><strong>Courbe de reference:</strong> {escape(str(row['reference_curve']))}</p>",
                    "</article>",
                ]
            )
        )
    return "\n".join(cards)


def build_proxy_validation_report_html(
    summary_df: pd.DataFrame,
    metadata_df: pd.DataFrame,
    figure_path: str | Path,
    scenario_name: str,
) -> str:
    figure_name = Path(figure_path).name
    return f"""<!DOCTYPE html>
<html lang="fr">
<head>
  <meta charset="utf-8">
  <title>Validation proxy - {escape(scenario_name)}</title>
  <style>
    body {{
      font-family: Georgia, "Times New Roman", serif;
      margin: 24px;
      color: #172033;
      background: #f7f5ef;
    }}
    h1, h2 {{
      margin-bottom: 0.35rem;
    }}
    .hero {{
      background: linear-gradient(135deg, #e8efe6, #f8f3e8);
      padding: 20px 24px;
      border: 1px solid #d3d7cf;
      border-radius: 14px;
      margin-bottom: 24px;
    }}
    .hero p {{
      margin: 0.3rem 0;
      max-width: 980px;
    }}
    img {{
      max-width: 100%;
      border: 1px solid #c9c7bf;
      border-radius: 12px;
      background: white;
    }}
    .report-table {{
      border-collapse: collapse;
      width: 100%;
      background: white;
    }}
    .report-table th, .report-table td {{
      border: 1px solid #d7d3cb;
      padding: 8px 10px;
      vertical-align: top;
      text-align: left;
      font-size: 0.94rem;
    }}
    .report-table th {{
      background: #ece7dd;
    }}
    .proxy-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
      gap: 16px;
    }}
    .proxy-card {{
      background: white;
      border: 1px solid #d7d3cb;
      border-radius: 12px;
      padding: 14px 16px;
    }}
    .proxy-card p {{
      margin: 0.4rem 0;
    }}
    code {{
      background: #efece4;
      padding: 1px 5px;
      border-radius: 6px;
    }}
  </style>
</head>
<body>
  <section class="hero">
    <h1>Validation temporelle par proxys</h1>
    <p><strong>Scenario:</strong> {escape(scenario_name)}</p>
    <p>Les courbes ci-dessous comparent, pour chaque proxy, la courbe de reference et la courbe modelee effectivement utilisees dans le calcul des metriques de correlation, RMSE et decalage du pic.</p>
    <p>La section suivante documente ce qui est utilise pour chaque proxy: type de metrique, population cible, formule interpretee, sources et courbe de reference horaire.</p>
  </section>

  <h2>Courbes comparees</h2>
  <p><img src="{escape(figure_name)}" alt="Courbes proxy validation"></p>

  <h2>Synthese metriques</h2>
  {_html_table(summary_df)}

  <h2>Definition des proxys</h2>
  <div class="proxy-grid">
    {_proxy_cards(metadata_df)}
  </div>
</body>
</html>
"""

