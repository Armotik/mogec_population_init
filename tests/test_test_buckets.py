from tests.conftest import _infer_test_bucket


def test_infer_test_bucket_marks_integration_when_session_fixture_used():
    is_integration, is_slow = _infer_test_bucket(
        {"config", "monkeypatch"},
        "tests/test_temporal.py::test_example",
    )

    assert is_integration is True
    assert is_slow is False


def test_infer_test_bucket_marks_slow_for_heavy_integration_files():
    is_integration, is_slow = _infer_test_bucket(
        {"bati_popule"},
        "tests/test_full_pipeline.py::test_full_pipeline_execution",
    )

    assert is_integration is True
    assert is_slow is True


def test_infer_test_bucket_marks_unit_without_integration_fixtures():
    is_integration, is_slow = _infer_test_bucket(
        {"tmp_path"},
        "tests/test_cli.py::test_cli_unknown_command_returns_error",
    )

    assert is_integration is False
    assert is_slow is False
