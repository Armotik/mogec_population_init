#!/usr/bin/env python3
"""
Genere un explorateur HTML des profils et des activites individuelles.
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
from src.visualization.profile_activity import export_profile_activity_explorer


def main() -> None:
    parser = argparse.ArgumentParser(description="Genere un explorateur HTML des profils MOGEC.")
    parser.add_argument("--config", default="config.yaml", help="Chemin vers le scenario YAML.")
    parser.add_argument(
        "--output-path",
        default="data/04_visualization/profile_activity_explorer.html",
        help="Fichier HTML de sortie.",
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s - %(message)s")
    config = load_config(ROOT_DIR / args.config)
    gdf = run_pipeline(config)
    output_path = export_profile_activity_explorer(gdf, config, ROOT_DIR / args.output_path)
    print(output_path)


if __name__ == "__main__":
    main()
