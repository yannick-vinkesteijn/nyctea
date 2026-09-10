"""Turn the declared catalogue into registrations."""

from nyctea.validators.catalogue import CATALOGUE
from nyctea.validators.decorators import build_validator
from nyctea.validators.registry import Registry

__all__ = ["register_builtins"]

_REGISTER = {
    "column_check": "register_column_check",
    "column_parser": "register_column_parser",
    "frame_check": "register_frame_check",
    "frame_parser": "register_frame_parser",
}


def register_builtins(registry: Registry) -> None:
    """Register every validator declared by decorator without a registry.

    The catalogue is the list, so a built-in cannot be written and exported but left
    unregistered. A validator only reaches the catalogue if its module was imported,
    which `nyctea.validators.builtins` is responsible for.

    Args:
        registry: Registry to register the declared validators in.

    Example:
        >>> from nyctea import Registry, register_builtins
        >>> registry = Registry()
        >>> register_builtins(registry)
    """
    for declared in CATALOGUE:
        getattr(registry, _REGISTER[declared.kind])(build_validator(declared))
