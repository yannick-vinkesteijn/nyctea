"""Lightweight package-level logging helpers."""

import logging
import os

DEFAULT_LEVEL = "INFO"
LOG_LEVEL_ENV = "NYCTEA_LOG_LEVEL"

LOG_FORMAT = "%(asctime)s | %(levelname)s | %(name)s | %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


def configure_logging(level: str | None = None) -> None:
    """Attach a stderr handler to the nyctea logger, for scripts and the CLI.

    Opt-in. An application should configure logging itself, through `logging` or
    whatever it already uses, and leave this alone. Nyctea does not call it for you.

    Args:
        level: Log level, overriding the NYCTEA_LOG_LEVEL env var and the default.
            Repeated calls do not attach duplicate handlers.
    """
    chosen_level = (level or os.getenv(LOG_LEVEL_ENV) or DEFAULT_LEVEL).upper()
    root = logging.getLogger("nyctea")

    if not any(isinstance(h, logging.StreamHandler) for h in root.handlers):
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter(fmt=LOG_FORMAT, datefmt=DATE_FORMAT))
        root.addHandler(handler)

    root.setLevel(chosen_level)


def get_logger(name: str | None = None) -> logging.Logger:
    """Return a namespaced logger.

    It attaches no handler and sets no level: an application decides those, and a
    library that decides them for you writes into a stream you did not choose.

    Args:
        name: Optional suffix added to the base nyctea namespace.

    Returns:
        logging.Logger: A logger under the nyctea namespace.
    """
    return logging.getLogger(f"nyctea{'.' + name if name else ''}")


__all__ = ["DEFAULT_LEVEL", "LOG_LEVEL_ENV", "configure_logging", "get_logger"]
