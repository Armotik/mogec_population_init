#!/usr/bin/env python3
"""
Execute une validation temporelle par proxys sur un ou plusieurs scenarios.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import pandas as pd

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.core.proxy_validation import CURVE_COLUMNS, SUMMARY_COLUMNS, evaluate_temporal_proxies
from src.pipeline import load_config, run_pipeline


logger = logging.getLogger(__name__)


def _scenario_specs_from_root_config(root_config: dict, root_config_path: Path, scenario_set: str) -> list[dict]:
    scenario_sets = root_config.get("proxy_validation", {}).get("scenario_sets", {})
    entries = scenario_sets.get(scenario_set, [])
    specs = []

    for entry in entries:
        if isinstance(entry, str):
            specs.append({"config_path": str((root_config_path.parent / entry).resolve())})
        elif isinstance(entry, dict) and entry.get("config_path"):
            specs.append(
                {
                    "config_path": str((root_config_path.parent / str(entry["config_path"])).resolve()),
                    "label": entry.get("label"),
                }
            )

    return specs


def _scenario_specs_from_args(config_paths: list[str], base_dir: Path) -> list[dict]:
    return [{"config_path": str((base_dir / config_path).resolve())} for config_path in config_paths]


def main() -> None:
    parser = argparse.ArgumentParser(description="Compare plusieurs scenarios MOGEC a des proxys temporels documentes.")
    parser.add_argument(
        "--config",
        default="config.yaml",
        help="Configuration racine, utilisee aussi pour charger `proxy_validation.scenario_sets`.",
    )
    parser.add_argument(
        "--configs",
        nargs="*",
        help="Liste explicite de scenarios YAML a executer. Si omise, le script utilise `proxy_validation.scenario_sets`.",
    )
    parser.add_argument(
        "--scenario-set",
        default="default",
        help="Nom du jeu de scenarios a utiliser depuis `proxy_validation.scenario_sets`.",
    )
    parser.add_argument(
        "--output-dir",
        default="data/04_visualization/proxy_validation",
        help="Dossier d'export des tableaux CSV.",
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s - %(message)s")

    root_config_path = (ROOT_DIR / args.config).resolve()
    root_config = load_config(root_config_path)

    if args.configs:
        scenario_specs = _scenario_specs_from_args(args.configs, ROOT_DIR)
    else:
        scenario_specs = _scenario_specs_from_root_config(root_config, root_config_path, args.scenario_set)
        if not scenario_specs:
            scenario_specs = [{"config_path": str(root_config_path)}]

    summary_frames = []
    curve_frames = []
    for scenario_spec in scenario_specs:
        config_path = Path(scenario_spec["config_path"]).resolve()
        logger.info("Execution du scenario %s", config_path)
        config = load_config(config_path)
        gdf = run_pipeline(config)
        summary, curves = evaluate_temporal_proxies(gdf, config)

        if "label" in scenario_spec and not summary.empty:
            summary["scenario_name"] = scenario_spec["label"]
        if "label" in scenario_spec and not curves.empty:
            curves["scenario_name"] = scenario_spec["label"]

        if not summary.empty:
            summary_frames.append(summary)
        if not curves.empty:
            curve_frames.append(curves)

    output_dir = (ROOT_DIR / args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    summary_table = pd.concat(summary_frames, ignore_index=True) if summary_frames else pd.DataFrame(columns=SUMMARY_COLUMNS)
    curves_table = pd.concat(curve_frames, ignore_index=True) if curve_frames else pd.DataFrame(columns=CURVE_COLUMNS)

    summary_path = output_dir / "proxy_validation_summary.csv"
    curves_path = output_dir / "proxy_validation_curves.csv"
    summary_table.to_csv(summary_path, index=False)
    curves_table.to_csv(curves_path, index=False)

    print(summary_path)
    print(curves_path)


if __name__ == "__main__":
    main()
