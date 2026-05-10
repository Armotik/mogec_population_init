"""
CLI unifiee MOGEC.
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

import pandas as pd

LOGGER = logging.getLogger(__name__)
PROJECT_ROOT = Path(__file__).resolve().parents[2]


def load_config(config_path: str | Path) -> dict:
    from src.pipeline import load_config as _load_config

    return _load_config(config_path)


def run_pipeline(config: dict):
    from src.pipeline import run_pipeline as _run_pipeline

    return _run_pipeline(config)


def run_pipeline_to_export(config_path: str | Path):
    from src.pipeline import run_pipeline_to_export as _run_pipeline_to_export

    return _run_pipeline_to_export(config_path)


def prepare_external_sources(config: dict):
    from src.io.external_data_preparation import prepare_external_sources as _prepare_external_sources

    return _prepare_external_sources(config)


def evaluate_temporal_proxies(gdf_model, config: dict):
    from src.core.proxy_validation import evaluate_temporal_proxies as _evaluate_temporal_proxies

    return _evaluate_temporal_proxies(gdf_model, config)


def summary_columns() -> list[str]:
    from src.core.proxy_validation import SUMMARY_COLUMNS

    return list(SUMMARY_COLUMNS)


def curve_columns() -> list[str]:
    from src.core.proxy_validation import CURVE_COLUMNS

    return list(CURVE_COLUMNS)


def _resolve_from_root(path_str: str) -> Path:
    path = Path(path_str).expanduser()
    if path.is_absolute():
        return path
    return (PROJECT_ROOT / path).resolve()


def _is_local_path(value: object) -> bool:
    if not isinstance(value, str):
        return False
    stripped = value.strip()
    if not stripped:
        return False
    if "://" in stripped:
        return False
    return True


def _collect_required_input_paths(config: dict) -> list[tuple[str, Path]]:
    checks: list[tuple[str, Path]] = []
    study_area = config.get("study_area", {})
    data_input = config.get("data_paths", {}).get("input", {})

    if _is_local_path(study_area.get("boundary_path")):
        checks.append(("study_area.boundary_path", Path(str(study_area["boundary_path"]))))

    for key, value in data_input.items():
        if key.endswith("_layer"):
            continue
        if _is_local_path(value):
            checks.append((f"data_paths.input.{key}", Path(str(value))))

    accommodation_cfg = config.get("non_residential_model", {}).get("accommodation", {})
    if accommodation_cfg.get("enabled", False):
        capacity_table = accommodation_cfg.get("capacity_table")
        if _is_local_path(capacity_table):
            checks.append(("non_residential_model.accommodation.capacity_table", Path(str(capacity_table))))

    for set_name, entries in config.get("proxy_validation", {}).get("scenario_sets", {}).items():
        if not isinstance(entries, list):
            continue
        for index, entry in enumerate(entries):
            if isinstance(entry, str) and _is_local_path(entry):
                checks.append((f"proxy_validation.scenario_sets.{set_name}[{index}]", Path(str(entry))))
            elif isinstance(entry, dict):
                config_path = entry.get("config_path")
                if _is_local_path(config_path):
                    checks.append((f"proxy_validation.scenario_sets.{set_name}[{index}].config_path", Path(str(config_path))))

    return checks


def _collect_output_parent_paths(config: dict) -> list[tuple[str, Path]]:
    checks: list[tuple[str, Path]] = []
    output_cfg = config.get("data_paths", {}).get("output", {})

    interim_dir = output_cfg.get("interim_dir")
    final_export = output_cfg.get("final_export")
    if _is_local_path(interim_dir):
        checks.append(("data_paths.output.interim_dir", Path(str(interim_dir))))
    if _is_local_path(final_export):
        checks.append(("data_paths.output.final_export.parent", Path(str(final_export)).parent))

    return checks


def _validate_paths_for_dry_run(config: dict, config_path: Path) -> None:
    missing_paths: list[str] = []

    for label, path in _collect_required_input_paths(config):
        candidate = path if path.is_absolute() else (config_path.parent / path).resolve()
        if not candidate.exists():
            missing_paths.append(f"{label} -> {candidate}")

    if missing_paths:
        message = "\n".join(missing_paths)
        raise ValueError(
            "Validation dry-run echouee: chemins d'entree manquants.\n"
            f"{message}"
        )

    unwritable: list[str] = []
    for label, path in _collect_output_parent_paths(config):
        candidate = path if path.is_absolute() else (config_path.parent / path).resolve()
        parent = candidate if candidate.suffix == "" else candidate.parent
        if not parent.exists():
            LOGGER.info("Creation du dossier de sortie manquant: %s", parent)
            parent.mkdir(parents=True, exist_ok=True)
        if not parent.is_dir():
            unwritable.append(f"{label} -> {parent} (n'est pas un dossier)")
            continue
        if not os_access_write(parent):
            unwritable.append(f"{label} -> {parent} (non inscriptible)")

    if unwritable:
        message = "\n".join(unwritable)
        raise ValueError(
            "Validation dry-run echouee: sorties non accessibles.\n"
            f"{message}"
        )


def os_access_write(path: Path) -> bool:
    return bool(os.access(path, os.W_OK | os.X_OK))


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


def _validate_referenced_proxy_configs(config: dict, config_path: Path) -> None:
    scenario_sets = config.get("proxy_validation", {}).get("scenario_sets", {})
    for set_name, entries in scenario_sets.items():
        if not isinstance(entries, list):
            continue
        for index, entry in enumerate(entries):
            if isinstance(entry, str):
                candidate = (config_path.parent / entry).resolve()
            elif isinstance(entry, dict) and entry.get("config_path"):
                candidate = (config_path.parent / str(entry["config_path"])).resolve()
            else:
                continue
            LOGGER.debug(
                "Validation dry-run config referencee: %s (set=%s, index=%s)",
                candidate,
                set_name,
                index,
            )
            load_config(candidate)


def _scenario_specs_from_args(config_paths: list[str], base_dir: Path) -> list[dict]:
    return [{"config_path": str((base_dir / config_path).resolve())} for config_path in config_paths]


def command_run(args: argparse.Namespace) -> int:
    LOGGER.info("Commande CLI: run (config=%s)", args.config)
    output_path = run_pipeline_to_export(args.config)
    print(output_path)
    return 0


def command_prepare(args: argparse.Namespace) -> int:
    LOGGER.info("Commande CLI: prepare (config=%s)", args.config)
    config = load_config(args.config)
    outputs = prepare_external_sources(config)
    for name, path in outputs.items():
        print(f"{name}: {path}")
    return 0


def command_validate(args: argparse.Namespace) -> int:
    LOGGER.info("Commande CLI: validate (dry-run, config=%s)", args.config)
    config_path = _resolve_from_root(args.config)
    config = load_config(config_path)
    LOGGER.debug("Validation schema complete du fichier: %s", config_path)
    _validate_paths_for_dry_run(config, config_path)
    _validate_referenced_proxy_configs(config, config_path)
    print(f"[OK] Validation dry-run reussie pour {config_path}")
    return 0


def command_explore(args: argparse.Namespace) -> int:
    LOGGER.info("Commande CLI: explore (mode=%s, config=%s)", args.mode, args.config)
    if args.mode == "html":
        from src.visualization.profile_activity import export_profile_activity_explorer

        config = load_config(_resolve_from_root(args.config))
        gdf = run_pipeline(config)
        output_path = export_profile_activity_explorer(gdf, config, _resolve_from_root(args.output_path))
        print(output_path)
        return 0

    from src.visualization.realtime_explorer import serve_realtime_explorer

    server = serve_realtime_explorer(_resolve_from_root(args.config), host=args.host, port=args.port)
    print(f"http://{args.host}:{args.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        LOGGER.info("Arret demande par l'utilisateur.")
    finally:
        server.server_close()
    return 0


def _render_proxy_report(config_path: Path, output_dir: Path, summary_df: pd.DataFrame, curves_df: pd.DataFrame) -> tuple[Path, Path, Path]:
    from src.visualization.proxy_validation_report import (
        build_proxy_validation_report_html,
        proxy_metadata_table,
        save_proxy_validation_figure,
    )

    config = load_config(config_path)
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
    return figure_path, html_path, metadata_path


def command_proxy_validate(args: argparse.Namespace) -> int:
    LOGGER.info(
        "Commande CLI: proxy-validate (config=%s, scenario_set=%s, output_dir=%s)",
        args.config,
        args.scenario_set,
        args.output_dir,
    )
    root_config_path = _resolve_from_root(args.config)
    root_config = load_config(root_config_path)

    if args.configs:
        scenario_specs = _scenario_specs_from_args(args.configs, PROJECT_ROOT)
    else:
        scenario_specs = _scenario_specs_from_root_config(root_config, root_config_path, args.scenario_set)
        if not scenario_specs:
            scenario_specs = [{"config_path": str(root_config_path)}]

    summary_frames = []
    curve_frames = []
    for scenario_spec in scenario_specs:
        config_path = Path(scenario_spec["config_path"]).resolve()
        LOGGER.info("Execution du scenario %s", config_path)
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

    output_dir = _resolve_from_root(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    summary_table = pd.concat(summary_frames, ignore_index=True) if summary_frames else pd.DataFrame(columns=summary_columns())
    curves_table = pd.concat(curve_frames, ignore_index=True) if curve_frames else pd.DataFrame(columns=curve_columns())

    summary_path = output_dir / "proxy_validation_summary.csv"
    curves_path = output_dir / "proxy_validation_curves.csv"
    summary_table.to_csv(summary_path, index=False)
    curves_table.to_csv(curves_path, index=False)

    print(summary_path)
    print(curves_path)

    if args.render_report:
        report_config_path = _resolve_from_root(args.report_config or args.config)
        figure_path, html_path, metadata_path = _render_proxy_report(
            report_config_path,
            output_dir,
            summary_table,
            curves_table,
        )
        print(figure_path)
        print(html_path)
        print(metadata_path)

    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="CLI unifiee MOGEC (run, prepare, validate, explore, proxy-validate)."
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="count",
        default=0,
        help="Augmente la verbosite CLI (`-v`=INFO, `-vv`=DEBUG).",
    )
    subparsers = parser.add_subparsers(dest="command")

    run_parser = subparsers.add_parser("run", help="Execute le pipeline complet et exporte le GeoPackage.")
    run_parser.add_argument("--config", default="config.yaml", help="Chemin vers le fichier de configuration YAML.")
    run_parser.set_defaults(handler=command_run)

    prepare_parser = subparsers.add_parser("prepare", help="Prepare les sources externes (restaurants, hebergements, plages).")
    prepare_parser.add_argument("--config", default="config.yaml", help="Chemin vers le fichier de configuration YAML.")
    prepare_parser.set_defaults(handler=command_prepare)

    validate_parser = subparsers.add_parser("validate", help="Valide la configuration sans executer le pipeline lourd (dry-run).")
    validate_parser.add_argument("--config", default="config.yaml", help="Chemin vers le fichier de configuration YAML.")
    validate_parser.set_defaults(handler=command_validate)

    explore_parser = subparsers.add_parser("explore", help="Explore les profils soit en web local, soit via export HTML.")
    explore_parser.add_argument("--config", default="config.yaml", help="Chemin vers le fichier de configuration YAML.")
    explore_parser.add_argument("--mode", choices=["web", "html"], default="web", help="Mode web serveur local ou export HTML statique.")
    explore_parser.add_argument("--host", default="127.0.0.1", help="Adresse d'ecoute du serveur local (mode web).")
    explore_parser.add_argument("--port", type=int, default=8765, help="Port du serveur local (mode web).")
    explore_parser.add_argument(
        "--output-path",
        default="data/04_visualization/profile_activity_explorer.html",
        help="Chemin du fichier HTML (mode html).",
    )
    explore_parser.set_defaults(handler=command_explore)

    proxy_parser = subparsers.add_parser("proxy-validate", help="Lance la validation par proxys sur un ou plusieurs scenarios.")
    proxy_parser.add_argument(
        "--config",
        default="config.yaml",
        help="Configuration racine, utilisee aussi pour charger `proxy_validation.scenario_sets`.",
    )
    proxy_parser.add_argument(
        "--configs",
        nargs="*",
        help="Liste explicite de scenarios YAML a executer. Si omise, utilisation de `proxy_validation.scenario_sets`.",
    )
    proxy_parser.add_argument(
        "--scenario-set",
        default="default",
        help="Nom du jeu de scenarios a utiliser depuis `proxy_validation.scenario_sets`.",
    )
    proxy_parser.add_argument(
        "--output-dir",
        default="data/04_visualization/proxy_validation",
        help="Dossier d'export des tableaux CSV.",
    )
    proxy_parser.add_argument(
        "--render-report",
        action="store_true",
        help="Genere aussi le PNG/HTML de synthese proxy a partir des CSV produits.",
    )
    proxy_parser.add_argument(
        "--report-config",
        default=None,
        help="Scenario YAML pour les metadonnees du rapport (par defaut: --config).",
    )
    proxy_parser.set_defaults(handler=command_proxy_validate)

    return parser


def main(argv: list[str] | None = None) -> int:
    raw_args = list(sys.argv[1:] if argv is None else argv)
    known_commands = {"run", "prepare", "validate", "explore", "proxy-validate"}
    if not raw_args:
        raw_args = ["run"]
    elif any(arg in known_commands for arg in raw_args):
        pass
    elif raw_args[0] in {"-h", "--help"}:
        pass
    else:
        prefix_idx = 0
        while prefix_idx < len(raw_args) and raw_args[prefix_idx] in {"-v", "-vv"}:
            prefix_idx += 1

        first_after_prefix = raw_args[prefix_idx] if prefix_idx < len(raw_args) else None
        if isinstance(first_after_prefix, str) and first_after_prefix.startswith("-"):
            raw_args = [*raw_args[:prefix_idx], "run", *raw_args[prefix_idx:]]

    parser = build_parser()
    try:
        args = parser.parse_args(raw_args)
    except SystemExit as exc:
        return int(exc.code)

    logging.basicConfig(level=logging.WARNING, format="%(levelname)s - %(message)s")
    cli_verbosity = int(getattr(args, "verbose", 0))
    if cli_verbosity >= 2:
        logging.getLogger("src").setLevel(logging.DEBUG)
        LOGGER.setLevel(logging.DEBUG)
    elif cli_verbosity == 1:
        logging.getLogger("src").setLevel(logging.INFO)
        LOGGER.setLevel(logging.INFO)

    if not hasattr(args, "handler"):
        parser.print_help()
        return 2

    try:
        LOGGER.debug("Arguments CLI resolves: %s", args)
        return int(args.handler(args))
    except ValueError as exc:
        LOGGER.error(str(exc))
        return 2
    except Exception as exc:  # pragma: no cover - garde-fou CLI
        LOGGER.exception("Echec d'execution: %s", exc)
        return 1
