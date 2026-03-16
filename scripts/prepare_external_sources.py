#!/usr/bin/env python3
"""
Prepare les sources externes telechargees pour le pipeline MOGEC.

Ce script produit les tables intermediaires pour les restaurants,
hebergements et plages, a partir des jeux telecharges dans `data/01_raw`.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.io.external_data_preparation import prepare_external_sources
from src.pipeline import load_config


def main() -> None:
    parser = argparse.ArgumentParser(description="Prepare les sources externes pour le pipeline MOGEC.")
    parser.add_argument("--config", default="config.yaml", help="Chemin vers le fichier de configuration.")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(name)s:%(message)s")
    config = load_config(args.config)
    outputs = prepare_external_sources(config)

    for name, path in outputs.items():
        print(f"{name}: {path}")


if __name__ == "__main__":
    main()
