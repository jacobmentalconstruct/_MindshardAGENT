"""Structured logging for the application runtime.

All application logging flows through this module.
No print() debugging in app runtime per contract rule 9.1.
"""

import logging
import os
from pathlib import Path


_LOG_FORMAT = "%(asctime)s [%(levelname)-7s] %(name)s: %(message)s"
_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

_initialized = False


def init_logging(log_dir: str | Path | None = None, level: int = logging.DEBUG) -> logging.Logger:
    """Initialize the application logging system.

    Sets up file handler (rolling) and a root logger.
    Returns the app root logger.
    """
    global _initialized
    if _initialized:
        return logging.getLogger("agentictoolbox")

    root = logging.getLogger("agentictoolbox")
    root.setLevel(level)

    formatter = logging.Formatter(_LOG_FORMAT, datefmt=_DATE_FORMAT)

    # Console handler at INFO level
    console = logging.StreamHandler()
    console.setLevel(logging.INFO)
    console.setFormatter(formatter)
    root.addHandler(console)

    # File handler if log_dir provided
    if log_dir:
        log_dir = Path(log_dir)
        log_dir.mkdir(parents=True, exist_ok=True)
        log_file = log_dir / "app.log"
        file_handler = logging.FileHandler(str(log_file), encoding="utf-8")
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(formatter)
        root.addHandler(file_handler)

    _initialized = True
    root.info("Logging initialized")
    return root


def get_logger(name: str) -> logging.Logger:
    """Get a child logger under the app namespace."""
    return logging.getLogger(f"agentictoolbox.{name}")
