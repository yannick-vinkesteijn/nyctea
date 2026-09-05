"""Regression tests for signature validation under postponed annotation evaluation.

This file intentionally uses `from __future__ import annotations`, unlike the rest
of the codebase, because the bug under test (#50) only reproduces when a
validator's defining module has postponed evaluation enabled: `inspect.signature`
then returns unresolved annotation strings unless resolved with `eval_str=True`.
"""

from __future__ import annotations

import polars as pl
import pytest

from nyctea.exceptions import RegistrationError
from nyctea.validators.base import ValidatorMetadata
from nyctea.validators.column import ColumnCheck
from nyctea.validators.frame import FrameCheck


def test_column_validator_registers_under_future_annotations():
    class FutureAnnotatedCheck(ColumnCheck):
        def execute(self, column: pl.Expr, **kwargs) -> pl.Expr:
            return column.is_not_null()

        def validate_args(self, **kwargs) -> None:
            pass

    check = FutureAnnotatedCheck(ValidatorMetadata(name="future_check"))
    assert check.name == "future_check"


def test_frame_validator_registers_under_future_annotations():
    class FutureAnnotatedFrameCheck(FrameCheck):
        def execute(self, frame: pl.LazyFrame, **kwargs) -> pl.LazyFrame:
            return frame

        def validate_args(self, **kwargs) -> None:
            pass

    check = FutureAnnotatedFrameCheck(ValidatorMetadata(name="future_frame_check"))
    assert check.name == "future_frame_check"


def test_column_validator_bad_annotation_raises():
    class BadAnnotationCheck(ColumnCheck):
        def execute(self, column: DoesNotExist, **kwargs) -> pl.Expr:  # noqa: F821  # ty: ignore[unresolved-reference]
            return column.is_not_null()

        def validate_args(self, **kwargs) -> None:
            pass

    with pytest.raises(RegistrationError, match="unresolvable annotation"):
        BadAnnotationCheck(ValidatorMetadata(name="bad_column_check"))


def test_frame_validator_bad_annotation_raises():
    class BadAnnotationFrameCheck(FrameCheck):
        def execute(self, frame: DoesNotExist, **kwargs) -> pl.LazyFrame:  # noqa: F821  # ty: ignore[unresolved-reference]
            return frame

        def validate_args(self, **kwargs) -> None:
            pass

    with pytest.raises(RegistrationError, match="unresolvable annotation"):
        BadAnnotationFrameCheck(ValidatorMetadata(name="bad_frame_check"))
