import pytest

from scripts import (
    generate_profile_activity_explorer,
    prepare_external_sources,
    run_proxy_validation,
    run_realtime_profile_explorer,
)


def test_prepare_wrapper_delegates_to_cli(monkeypatch):
    captured = {}

    def fake_cli_main(args):
        captured["args"] = list(args)
        return 0

    monkeypatch.setattr(prepare_external_sources, "cli_main", fake_cli_main)

    with pytest.raises(SystemExit) as exc:
        prepare_external_sources.main()

    assert exc.value.code == 0
    assert captured["args"][0] == "prepare"


def test_proxy_validate_wrapper_delegates_to_cli(monkeypatch):
    captured = {}

    def fake_cli_main(args):
        captured["args"] = list(args)
        return 0

    monkeypatch.setattr(run_proxy_validation, "cli_main", fake_cli_main)

    with pytest.raises(SystemExit) as exc:
        run_proxy_validation.main()

    assert exc.value.code == 0
    assert captured["args"][0] == "proxy-validate"


def test_explore_html_wrapper_delegates_to_cli(monkeypatch):
    captured = {}

    def fake_cli_main(args):
        captured["args"] = list(args)
        return 0

    monkeypatch.setattr(generate_profile_activity_explorer, "cli_main", fake_cli_main)

    with pytest.raises(SystemExit) as exc:
        generate_profile_activity_explorer.main()

    assert exc.value.code == 0
    assert captured["args"][:3] == ["explore", "--mode", "html"]


def test_explore_web_wrapper_delegates_to_cli(monkeypatch):
    captured = {}

    def fake_cli_main(args):
        captured["args"] = list(args)
        return 0

    monkeypatch.setattr(run_realtime_profile_explorer, "cli_main", fake_cli_main)

    with pytest.raises(SystemExit) as exc:
        run_realtime_profile_explorer.main()

    assert exc.value.code == 0
    assert captured["args"][:3] == ["explore", "--mode", "web"]
