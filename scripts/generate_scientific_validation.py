#!/usr/bin/env python3
"""
Genere un dossier de validation scientifique a partir d'un scenario MOGEC.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import geopandas as gpd

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.pipeline import load_config, run_pipeline_to_export
from src.visualization.validation import (
    evidence_traceability_report,
    external_proxy_validation,
    hourly_population_profile,
    non_residential_validation,
    occupied_buildings_by_usage,
    plot_scientific_validation_dashboard,
    role_targets_vs_realized,
    scientific_methodology_checklist,
    structural_quality_report,
    summarize_export_metrics,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Genere les sorties de validation scientifique du scenario.")
    parser.add_argument("--config", default="config.yaml", help="Chemin vers le fichier YAML du scenario.")
    parser.add_argument(
        "--output-dir",
        default="data/04_visualization/validation",
        help="Dossier de sortie pour le dashboard et les tableaux CSV.",
    )
    parser.add_argument(
        "--force-export",
        action="store_true",
        help="Regenere le GeoPackage final avant de produire la validation.",
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s - %(message)s")

    config_path = ROOT_DIR / args.config
    config = load_config(config_path)
    export_path = ROOT_DIR / config["data_paths"]["output"]["final_export"]

    if args.force_export or not export_path.exists():
        logging.info("Generation ou regeneration de l'export final...")
        export_path = run_pipeline_to_export(config_path)

    gdf = gpd.read_file(export_path)

    output_dir = ROOT_DIR / args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    dashboard_path = plot_scientific_validation_dashboard(
        gdf,
        config,
        output_dir / "validation_dashboard.png",
    )

    tables = {
        "structural_quality.csv": structural_quality_report(gdf),
        "export_metrics.csv": summarize_export_metrics(gdf),
        "hourly_profile.csv": hourly_population_profile(gdf),
        "role_targets_vs_realized.csv": role_targets_vs_realized(gdf, config),
        "non_residential_validation.csv": non_residential_validation(gdf),
        "occupied_buildings_by_usage.csv": occupied_buildings_by_usage(gdf),
        "evidence_traceability.csv": evidence_traceability_report(config),
        "scientific_methodology_checklist.csv": scientific_methodology_checklist(gdf, config),
        "external_proxy_validation.csv": external_proxy_validation(gdf, config),
    }

    for filename, table in tables.items():
        table.to_csv(output_dir / filename, index=False)

    print(dashboard_path)
    for filename in tables:
        print(output_dir / filename)


if __name__ == "__main__":
    main()
