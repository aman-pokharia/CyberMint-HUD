from __future__ import annotations

import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path


def configure_logging() -> logging.Logger:
    logger = logging.getLogger("cybermint_hud")
    logger.setLevel(logging.INFO)
    if logger.handlers:
        return logger
    state_home = os.environ.get("XDG_STATE_HOME") or str(Path(os.environ.get("HOME", str(Path.home()))) / ".local" / "state")
    log_dir = Path(state_home) / "cybermint-hud"
    try:
        log_dir.mkdir(parents=True, exist_ok=True)
        handler: logging.Handler = RotatingFileHandler(log_dir / "hud.log", maxBytes=512 * 1024, backupCount=2, encoding="utf-8")
    except OSError:
        handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    logger.addHandler(handler)
    logger.propagate = False
    return logger
