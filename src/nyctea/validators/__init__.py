"""Validator base classes and the decorator/registry API that extends them."""

from nyctea.validators.base import Validator, ValidatorMetadata
from nyctea.validators.builtins.register import register_builtins
from nyctea.validators.column import ColumnCheck, ColumnParser, ColumnValidator
from nyctea.validators.decorators import checker, frame_checker, frame_parser, parser
from nyctea.validators.frame import FrameCheck, FrameParser, FrameValidator
from nyctea.validators.registry import Registry, ValidatorRegistry

__all__ = [
    "ColumnCheck",
    "ColumnParser",
    "ColumnValidator",
    "FrameCheck",
    "FrameParser",
    "FrameValidator",
    "Registry",
    "Validator",
    "ValidatorMetadata",
    "ValidatorRegistry",
    "checker",
    "frame_checker",
    "frame_parser",
    "parser",
    "register_builtins",
]
