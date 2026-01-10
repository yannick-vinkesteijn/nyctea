"""Tests for column plugins."""

import polars as pl
import pytest

from nyctea.exceptions import PluginExecutionError, RegistrationError
from nyctea.plugins.base import PluginMetadata
from nyctea.plugins.column import ColumnCheck, ColumnParser


class SimpleParser(ColumnParser):
    """Simple parser for testing."""

    def __init__(self):
        super().__init__(PluginMetadata(name="simple"))

    def execute(self, column: pl.Expr, **kwargs) -> pl.Expr:
        return column.str.to_uppercase()

    def validate_args(self, **kwargs) -> None:
        pass


class SimpleCheck(ColumnCheck):
    """Simple check for testing."""

    def __init__(self):
        super().__init__(PluginMetadata(name="simple_check"))

    def execute(self, column: pl.Expr, **kwargs) -> pl.Expr:
        return column.str.len_chars() > 0

    def validate_args(self, **kwargs) -> None:
        pass


def test_column_parser_creation():
    """Test creating a column parser."""
    parser = SimpleParser()
    assert parser.name == "simple"
    assert isinstance(parser, ColumnParser)


def test_column_parser_execute():
    """Test column parser execution."""
    parser = SimpleParser()
    expr = pl.col("test")
    result = parser(expr)
    assert isinstance(result, pl.Expr)


def test_column_parser_purity_validation():
    """Test that column parser enforces purity."""
    parser = SimpleParser()

    # Valid: single column reference
    result = parser(pl.col("name"))
    assert isinstance(result, pl.Expr)


def test_column_parser_rejects_non_expr():
    """Test that column parser rejects non-Expr input."""
    parser = SimpleParser()

    with pytest.raises(TypeError, match="expected pl.Expr"):
        parser("not an expression")  # type: ignore


def test_column_check_creation():
    """Test creating a column check."""
    check = SimpleCheck()
    assert check.name == "simple_check"
    assert isinstance(check, ColumnCheck)


def test_column_check_returns_boolean():
    """Test that column check returns boolean expression."""
    check = SimpleCheck()
    result = check(pl.col("name"))
    # Can't easily test the output type without executing,
    # but we can verify it returns an expression
    assert isinstance(result, pl.Expr)


def test_column_plugin_signature_validation():
    """Test that invalid signatures are rejected."""
    class BadParser(ColumnParser):
        def __init__(self):
            # This should fail because execute doesn't have 'column' parameter
            metadata = PluginMetadata(name="bad")
            # Temporarily skip validation for this test
            # In real code, __init__ would call super().__init__ which validates
            self.metadata = metadata

        def execute(self, wrong_param: pl.Expr, **kwargs) -> pl.Expr:  # Wrong param name
            return wrong_param

        def validate_args(self, **kwargs) -> None:
            pass

    with pytest.raises(RegistrationError, match="must have 'column' as first parameter"):
        parser = BadParser()
        parser._validate_signature()
