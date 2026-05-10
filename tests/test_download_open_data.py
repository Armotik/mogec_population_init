from __future__ import annotations

import hashlib
import os
import subprocess
from pathlib import Path


REQUIRED_FILES = [
    "data/01_raw/tourisme_pdl/restaurants_pdl.csv",
    "data/01_raw/tourisme_pdl/hotels_pdl.csv",
    "data/01_raw/tourisme_pdl/campings_pdl.csv",
    "data/01_raw/tourisme_pdl/residences_tourisme_pdl.csv",
    "data/01_raw/tourisme_pdl/hebergements_collectifs_pdl.csv",
    "data/01_raw/tourisme_pdl/hebergements_locatifs_pdl.csv",
    "data/01_raw/plages/plages_sable_loire_atlantique.zip",
    "data/01_raw/insee_tourisme/capacites_hebergements_touristiques.zip",
]


def _write_file(root: Path, relative_path: str, payload: bytes) -> str:
    absolute_path = root / relative_path
    absolute_path.parent.mkdir(parents=True, exist_ok=True)
    absolute_path.write_bytes(payload)
    return hashlib.sha256(payload).hexdigest()


def _build_manifest(root: Path, *, bad_hash_for: str | None = None) -> Path:
    manifest_path = root / "docs" / "open_data_checksums.sha256"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []
    for relative_path in REQUIRED_FILES:
        payload = f"payload::{relative_path}".encode("utf-8")
        sha = _write_file(root, relative_path, payload)
        if relative_path == bad_hash_for:
            sha = "0" * 64
        lines.append(f"{sha} {relative_path}")
    manifest_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return manifest_path


def _run_download_script(tmp_root: Path, checksum_file: Path) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["MOGEC_ROOT_DIR"] = str(tmp_root)
    env["MOGEC_CHECKSUM_FILE"] = str(checksum_file)
    env["MOGEC_SKIP_DOWNLOADS"] = "1"
    env["MOGEC_SKIP_UNZIP"] = "1"
    return subprocess.run(
        ["bash", "scripts/download_open_data.sh"],
        cwd=Path(__file__).resolve().parents[1],
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )


def test_download_open_data_script_verifies_checksums_in_skip_mode(tmp_path):
    checksum_file = _build_manifest(tmp_path)
    result = _run_download_script(tmp_path, checksum_file)

    assert result.returncode == 0
    assert "checksum verification" in result.stdout.lower()


def test_download_open_data_script_fails_on_checksum_mismatch(tmp_path):
    checksum_file = _build_manifest(
        tmp_path,
        bad_hash_for="data/01_raw/tourisme_pdl/restaurants_pdl.csv",
    )
    result = _run_download_script(tmp_path, checksum_file)

    assert result.returncode != 0
    assert "Checksum mismatch for data/01_raw/tourisme_pdl/restaurants_pdl.csv" in result.stderr
