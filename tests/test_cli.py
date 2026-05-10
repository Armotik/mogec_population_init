from pathlib import Path

import pandas as pd

from src.cli import app


def test_cli_defaults_to_run_when_no_subcommand(monkeypatch):
    captured = {}

    def fake_run_pipeline_to_export(config_path):
        captured["config_path"] = str(config_path)
        return Path("/tmp/fake_export.gpkg")

    monkeypatch.setattr(app, "run_pipeline_to_export", fake_run_pipeline_to_export)

    code = app.main(["--config", "config_summer_day.yaml"])

    assert code == 0
    assert captured["config_path"] == "config_summer_day.yaml"


def test_cli_defaults_to_run_with_verbose_flags(monkeypatch):
    captured = {}

    def fake_run_pipeline_to_export(config_path):
        captured["config_path"] = str(config_path)
        return Path("/tmp/fake_export.gpkg")

    monkeypatch.setattr(app, "run_pipeline_to_export", fake_run_pipeline_to_export)

    code = app.main(["-vv", "--config", "config.yaml"])

    assert code == 0
    assert captured["config_path"] == "config.yaml"


def test_cli_unknown_command_returns_error():
    code = app.main(["unknown-command"])
    assert code == 2


def test_cli_validate_dry_run_fails_on_missing_inputs(monkeypatch, tmp_path):
    config = {
        "study_area": {"boundary_path": str(tmp_path / "missing_boundary.gpkg")},
        "data_paths": {
            "input": {"bd_topo": str(tmp_path / "missing_bdto.gpkg")},
            "output": {
                "interim_dir": str(tmp_path),
                "final_export": str(tmp_path / "out.gpkg"),
            },
        },
        "non_residential_model": {"accommodation": {"enabled": False}},
        "proxy_validation": {"scenario_sets": {}},
    }

    monkeypatch.setattr(app, "load_config", lambda *_args, **_kwargs: config)

    code = app.main(["validate", "--config", str(tmp_path / "config.yaml")])
    assert code == 2


def test_cli_validate_dry_run_success(monkeypatch, tmp_path):
    boundary = tmp_path / "boundary.gpkg"
    bd_topo = tmp_path / "bdtopo.gpkg"
    boundary.write_text("ok", encoding="utf-8")
    bd_topo.write_text("ok", encoding="utf-8")

    config = {
        "study_area": {"boundary_path": str(boundary)},
        "data_paths": {
            "input": {"bd_topo": str(bd_topo)},
            "output": {
                "interim_dir": str(tmp_path),
                "final_export": str(tmp_path / "out.gpkg"),
            },
        },
        "non_residential_model": {"accommodation": {"enabled": False}},
        "proxy_validation": {"scenario_sets": {}},
    }

    monkeypatch.setattr(app, "load_config", lambda *_args, **_kwargs: config)

    code = app.main(["validate", "--config", str(tmp_path / "config.yaml")])
    assert code == 0


def test_cli_validate_dry_run_loads_proxy_referenced_configs(monkeypatch, tmp_path):
    referenced = tmp_path / "scenario_referenced.yaml"
    referenced.write_text("ok", encoding="utf-8")

    root_config = {
        "study_area": {"boundary_path": str(tmp_path / "boundary.gpkg")},
        "data_paths": {
            "input": {"bd_topo": str(tmp_path / "bdtopo.gpkg")},
            "output": {
                "interim_dir": str(tmp_path),
                "final_export": str(tmp_path / "out.gpkg"),
            },
        },
        "non_residential_model": {"accommodation": {"enabled": False}},
        "proxy_validation": {
            "scenario_sets": {
                "default": [
                    {"config_path": str(referenced)},
                ]
            }
        },
    }

    (tmp_path / "boundary.gpkg").write_text("ok", encoding="utf-8")
    (tmp_path / "bdtopo.gpkg").write_text("ok", encoding="utf-8")

    seen_paths = []

    def fake_load_config(path, *_args, **_kwargs):
        seen_paths.append(Path(path).resolve())
        return root_config if len(seen_paths) == 1 else {"scenario": {"name": "ref"}}

    monkeypatch.setattr(app, "load_config", fake_load_config)

    code = app.main(["validate", "--config", str(tmp_path / "config.yaml")])
    assert code == 0
    assert referenced.resolve() in seen_paths


def test_cli_proxy_validate_writes_csv_outputs(monkeypatch, tmp_path):
    root_config = {
        "proxy_validation": {"scenario_sets": {}},
    }
    scenario_config = {"scenario": {"name": "test"}}

    root_config_path = tmp_path / "root.yaml"
    scenario_path = tmp_path / "scenario.yaml"
    root_config_path.write_text("placeholder", encoding="utf-8")
    scenario_path.write_text("placeholder", encoding="utf-8")

    def fake_load_config(path):
        resolved = Path(path).resolve()
        if resolved == root_config_path.resolve():
            return root_config
        return scenario_config

    monkeypatch.setattr(app, "load_config", fake_load_config)
    monkeypatch.setattr(app, "run_pipeline", lambda _config: "fake_gdf")
    monkeypatch.setattr(
        app,
        "evaluate_temporal_proxies",
        lambda *_args, **_kwargs: (
            pd.DataFrame([{"scenario_name": "test", "proxy_id": "p1", "status": "pass"}]),
            pd.DataFrame([{"scenario_name": "test", "proxy_id": "p1", "hour": 0, "modeled_value": 0.0, "reference_value": 0.0}]),
        ),
    )

    output_dir = tmp_path / "proxy_output"
    code = app.main(
        [
            "proxy-validate",
            "--config",
            str(root_config_path),
            "--configs",
            str(scenario_path),
            "--output-dir",
            str(output_dir),
        ]
    )

    assert code == 0
    assert (output_dir / "proxy_validation_summary.csv").exists()
    assert (output_dir / "proxy_validation_curves.csv").exists()
