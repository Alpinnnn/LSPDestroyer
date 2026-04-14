from __future__ import annotations

import argparse

from .app import LspDestroyerApp
from .constants import APP_TITLE


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog=APP_TITLE)
    parser.add_argument("--self-test", action="store_true", help=argparse.SUPPRESS)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    app = LspDestroyerApp(self_test=args.self_test)
    try:
        app.run()
    finally:
        if not app.exiting:
            app.shutdown()
