"""
Point d'entree CLI unifie du projet MOGEC.
"""

from __future__ import annotations

import sys

from src.cli import main as cli_main


def main() -> int:
    return cli_main()


if __name__ == "__main__":
    raise SystemExit(main())
