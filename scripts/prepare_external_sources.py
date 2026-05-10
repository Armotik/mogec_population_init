#!/usr/bin/env python3
"""
Compatibilite: delegue vers `main.py prepare`.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.cli import main as cli_main


def main() -> None:
    raise SystemExit(cli_main(["prepare", *sys.argv[1:]]))


if __name__ == "__main__":
    main()
