"""Lightweight package-level logging helpers."""

import logging
import os

DEFAULT_LEVEL = "INFO"
LOG_LEVEL_ENV = "NYCTEA_LOG_LEVEL"

LOG_FORMAT = "%(asctime)s | %(levelname)s | %(name)s | %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


def configure_logging(level: str | None = None) -> None:
    """Configure package-wide logging once.

    Args:
        level: Log level, overriding the NYCTEA_LOG_LEVEL env var and the default.
            Repeated calls do not attach duplicate handlers.
    """
    chosen_level = (level or os.getenv(LOG_LEVEL_ENV) or DEFAULT_LEVEL).upper()
    root = logging.getLogger("nyctea")

    if not root.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter(fmt=LOG_FORMAT, datefmt=DATE_FORMAT))
        root.addHandler(handler)

    root.setLevel(chosen_level)


def get_logger(name: str | None = None) -> logging.Logger:
    """Return a namespaced logger, configuring the package logger if needed.

    Args:
        name: Optional suffix added to the base nyctea namespace.

    Returns:
        logging.Logger: A configured logger instance.
    """
    configure_logging()
    qualified_name = f"nyctea{'.' + name if name else ''}"
    return logging.getLogger(qualified_name)


__all__ = ["DEFAULT_LEVEL", "LOG_LEVEL_ENV", "configure_logging", "get_logger"]
