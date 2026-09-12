"""Nyctea emits log records; the application decides what happens to them."""

import logging
import subprocess
import sys

from nyctea.utils.logger import configure_logging, get_logger


def test_import_attaches_no_stream_handler():
    """Importing Nyctea must not write into an application's stderr.

    Run in a subprocess because the handler is attached at import, and this module's
    own imports have already run by the time a test executes.
    """
    code = "import logging, nyctea; print([type(h).__name__ for h in logging.getLogger('nyctea').handlers])"
    out = subprocess.run(  # noqa: S603
        [sys.executable, "-c", code], capture_output=True, text=True, check=True
    )

    assert out.stdout.strip() == "['NullHandler']"
    assert out.stderr == ""


def test_import_sets_no_level():
    """A level belongs to the application, so the package logger stays at NOTSET."""
    code = "import logging, nyctea; print(logging.getLogger('nyctea').level)"
    out = subprocess.run(  # noqa: S603
        [sys.executable, "-c", code], capture_output=True, text=True, check=True
    )

    assert out.stdout.strip() == "0"


def test_null_handler_survives_a_reload():
    """Reloading the package must not stack a second handler on the same logger."""
    import importlib

    import nyctea

    for _ in range(2):
        importlib.reload(nyctea)

    nulls = [h for h in logging.getLogger("nyctea").handlers if isinstance(h, logging.NullHandler)]
    assert len(nulls) == 1


def test_get_logger_is_namespaced():
    assert get_logger("engine.pipeline").name == "nyctea.engine.pipeline"
    assert get_logger().name == "nyctea"


def test_get_logger_configures_nothing():
    """It used to call `configure_logging`, so importing any submodule configured logging."""
    logger = get_logger("probe")

    assert logger.handlers == []
    assert logger.level == logging.NOTSET


def test_opt_in_attaches_one_handler():
    """`configure_logging` stays available for scripts, and repeats do not stack up."""
    package_logger = logging.getLogger("nyctea")
    original = list(package_logger.handlers)
    try:
        package_logger.handlers = [logging.NullHandler()]
        configure_logging("DEBUG")
        configure_logging("DEBUG")

        streams = [h for h in package_logger.handlers if isinstance(h, logging.StreamHandler)]
        assert len(streams) == 1
        assert package_logger.level == logging.DEBUG
    finally:
        package_logger.handlers = original
        package_logger.setLevel(logging.NOTSET)
