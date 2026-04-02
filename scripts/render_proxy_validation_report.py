#!/usr/bin/env python3
"""
Genere une visualisation lisible des courbes de validation proxy.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.pipeline import load_config
from src.visualization.proxy_validation_report import (
    build_proxy_validation_report_html,
    proxy_metadata_table,
    save_proxy_validation_figure,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Produit une image et un rapport HTML a partir des sorties CSV de validation proxy.")
    parser.add_argument("--config", default="config_weekday_school_day.yaml", help="Scenario YAML a documenter.")
    parser.add_argument("--output-dir", default="data/04_visualization/proxy_validation", help="Dossier contenant `proxy_validation_summary.csv` et `proxy_validation_curves.csv`.")
    args = parser.parse_args()

    config_path = (ROOT_DIR / args.config).resolve()
    output_dir = (ROOT_DIR / args.output_dir).resolve()
    summary_path = output_dir / "proxy_validation_summary.csv"
    curves_path = output_dir / "proxy_validation_curves.csv"

    if not summary_path.exists():
        raise FileNotFoundError(f"Fichier introuvable: {summary_path}")
    if not curves_path.exists():
        raise FileNotFoundError(f"Fichier introuvable: {curves_path}")

    config = load_config(config_path)
    summary_df = pd.read_csv(summary_path)
    curves_df = pd.read_csv(curves_path)
    metadata_df = proxy_metadata_table(config)

    figure_path = output_dir / "proxy_validation_report.png"
    html_path = output_dir / "proxy_validation_report.html"
    metadata_path = output_dir / "proxy_validation_metadata.csv"

    save_proxy_validation_figure(summary_df, curves_df, figure_path)
    metadata_df.to_csv(metadata_path, index=False)
    html_path.write_text(
        build_proxy_validation_report_html(
            summary_df=summary_df,
            metadata_df=metadata_df,
            figure_path=figure_path,
            scenario_name=str(config.get("scenario", {}).get("name", "scenario")),
        ),
        encoding="utf-8",
    )

    print(figure_path)
    print(html_path)
    print(metadata_path)


if __name__ == "__main__":
    main()
