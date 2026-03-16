#!/usr/bin/env python3
"""
Genere une visualisation synthetique des destinations du modele.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.pipeline import load_config, run_pipeline
from src.visualization.destination_flows import plot_destination_flows


def main() -> None:
    parser = argparse.ArgumentParser(description="Genere la visualisation des flux de destination.")
    parser.add_argument("--config", default="config.yaml", help="Chemin vers la configuration YAML.")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s - %(message)s")
    config = load_config(args.config)
    gdf = run_pipeline(config)
    output_path = config.get("visualization", {}).get("destination_flows", {}).get(
        "output_path",
        "data/04_visualization/batz_destination_flows.png",
    )
    path = plot_destination_flows(gdf, output_path, config)
    print(path)


if __name__ == "__main__":
    main()
