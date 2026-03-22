#!/usr/bin/env python3
"""
Lance un explorateur web local des profils, foyers et trajectoires.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.visualization.realtime_explorer import serve_realtime_explorer


def main() -> None:
    parser = argparse.ArgumentParser(description="Lance un serveur web local pour explorer les profils MOGEC.")
    parser.add_argument("--config", default="config.yaml", help="Chemin vers le scenario YAML.")
    parser.add_argument("--host", default="127.0.0.1", help="Adresse d'ecoute du serveur local.")
    parser.add_argument("--port", type=int, default=8765, help="Port du serveur local.")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s - %(message)s")
    server = serve_realtime_explorer(ROOT_DIR / args.config, host=args.host, port=args.port)
    print(f"http://{args.host}:{args.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.server_close()


if __name__ == "__main__":
    main()
