from __future__ import annotations

import argparse
import sys

from .compat import compatibility_report
from .config import load_config
from .logging_setup import configure_logging


def main() -> int:
    parser = argparse.ArgumentParser(
        description="CyberMint HUD — Cyberpunk Desktop HUD for Linux Mint Cinnamon"
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Check environment, dependencies, and session compatibility without launching HUD",
    )
    parser.add_argument(
        "--toggle-launcher",
        action="store_true",
        help="Show or hide the app launcher in the running HUD (starts the HUD if it is not running)",
    )
    args = parser.parse_args()

    logger = configure_logging()
    config = load_config(logger=logger)
    report = compatibility_report()

    if args.check:
        print("=== CyberMint HUD Compatibility & Environment Check ===")
        for line in report.lines:
            print(f"  * {line}")
        print("=======================================================")
        return 0 if report.gtk_available else 1

    if not report.gtk_available:
        print(
            "CyberMint HUD requires GTK 3 and PyGObject bindings.\n"
            "Run 'python3 -m cybermint_hud --check' for diagnostic details.\n"
            "On Linux Mint, verify: python3-gi, python3-gi-cairo, gir1.2-gtk-3.0",
            file=sys.stderr,
        )
        logger.error("GTK 3 runtime unavailable: %s", report.gtk_error)
        return 1

    from .ui import run

    return run(config=config, logger=logger, report=report, toggle_launcher=args.toggle_launcher)


if __name__ == "__main__":
    raise SystemExit(main())
