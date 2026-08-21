"""Tests for decorator-based plugin registration."""

import polars as pl
import pytest

from nyctea import Registry, SchemaModel, register_builtins
from nyctea.exceptions import RegistrationError
from nyctea.plugins.decorators import ValidatorDecorator


class TestColumnParserDecorator:
    """Tests for column_parser decorator."""

    def test_basic_registration(self):
        """Test basic parser registration via decorator."""
        registry = Registry()
        decorators = ValidatorDecorator(registry)

        @decorators.column_parser(name="test_trim")
        def trim(column: pl.Expr) -> pl.Expr:
            return column.str.strip_chars()

        # Verify plugin was registered
        assert "test_trim" in registry.column_parsers.list_names()

        # Verify we can retrieve it
        plugin = registry.column_parsers.get("test_trim")
        assert plugin.name == "test_trim"

    def test_with_metadata(self):
        """Test parser with full metadata."""
        registry = Registry()
        decorators = ValidatorDecorator(registry)

        @decorators.column_parser(
            name="uppercase",
            description="Convert to uppercase",
            version="2.0.0",
            tags=["string", "formatting"],
            author="Test Author",
        )
        def to_upper(column: pl.Expr) -> pl.Expr:
            return column.str.to_uppercase()

        plugin = registry.column_parsers.get("uppercase")
        assert plugin.metadata.name == "uppercase"
        assert plugin.metadata.description == "Convert to uppercase"
        assert plugin.metadata.version == "2.0.0"
        assert "string" in plugin.metadata.tags
        assert "formatting" in plugin.metadata.tags
        assert plugin.metadata.author == "Test Author"

    def test_functional_usage(self):
        """Test that decorated function still works as a function."""
        registry = Registry()
        decorators = ValidatorDecorator(registry)

        @decorators.column_parser(name="double")
        def double_val(column: pl.Expr) -> pl.Expr:
            return column * 2

        # Function should still be callable
        df = pl.DataFrame({"x": [1, 2, 3]})
        result = df.select(double_val(pl.col("x")))
        assert result["x"].to_list() == [2, 4, 6]

    def test_integration_with_schema(self):
        """Test decorator-registered parser works in schema validation."""
        registry = Registry()
        register_builtins(registry)
        decorators = ValidatorDecorator(registry)

        @decorators.column_parser(name="custom_trim")
        def trim(column: pl.Expr) -> pl.Expr:
            return column.str.strip_chars()

        schema = SchemaModel.from_dict({
            "columns": {
                "text": {
                    "dtype": "Utf8",
                    "parsers": [{"name": "custom_trim"}],
                    "nullable": False,
                },
            }
        })

        df = pl.DataFrame({"text": ["  hello  ", "  world  "]})
        result = schema.validate(df, registry)
        assert result.data.collect()["text"].to_list() == ["hello", "world"]


class TestColumnCheckDecorator:
    """Tests for column_check decorator."""

    def test_basic_registration(self):
        """Test basic check registration via decorator."""
        registry = Registry()
        decorators = ValidatorDecorator(registry)

        @decorators.column_check(name="test_positive")
        def is_positive(column: pl.Expr) -> pl.Expr:
            return column > 0

        # Verify plugin was registered
        assert "test_positive" in registry.column_checks.list_names()

        # Verify we can retrieve it
        plugin = registry.column_checks.get("test_positive")
        assert plugin.name == "test_positive"

    def test_with_metadata(self):
        """Test check with full metadata."""
        registry = Registry()
        decorators = ValidatorDecorator(registry)

        @decorators.column_check(
            name="not_empty",
            description="Check string not empty",
            version="1.5.0",
            tags=["string", "validation"],
        )
        def check_not_empty(column: pl.Expr) -> pl.Expr:
            return column.str.len_chars() > 0

        plugin = registry.column_checks.get("not_empty")
        assert plugin.metadata.name == "not_empty"
        assert plugin.metadata.description == "Check string not empty"
        assert plugin.metadata.version == "1.5.0"
        assert "string" in plugin.metadata.tags

    def test_integration_with_schema(self):
        """Test decorator-registered check works in schema validation."""
        registry = Registry()
        register_builtins(registry)
        decorators = ValidatorDecorator(registry)

        @decorators.column_check(name="positive", tags=["numeric"])
        def is_positive(column: pl.Expr) -> pl.Expr:
            return column > 0

        schema = SchemaModel.from_dict({
            "columns": {
                "value": {
                    "dtype": "Int64",
                    "parsers": [{"name": "to_int"}],
                    "checks": [{"name": "positive"}],
                    "nullable": False,
                },
            }
        })

        # Test with valid data
        df_good = pl.DataFrame({"value": ["1", "2", "3"]})
        result_good = schema.validate(df_good, registry)
        assert result_good.report.rows_valid == 3

        # Test with invalid data
        df_bad = pl.DataFrame({"value": ["1", "-2", "3"]})
        result_bad = schema.validate(df_bad, registry)
        assert result_bad.report.rows_valid < result_bad.report.rows_processed


class TestDecoratorEdgeCases:
    """Tests for edge cases and error handling."""

    def test_duplicate_registration_raises_error(self):
        """Test that registering duplicate name raises error."""
        registry = Registry()
        decorators = ValidatorDecorator(registry)

        @decorators.column_parser(name="duplicate")
        def first(column: pl.Expr) -> pl.Expr:
            return column

        with pytest.raises(RegistrationError):
            @decorators.column_parser(name="duplicate")
            def second(column: pl.Expr) -> pl.Expr:
                return column

    def test_docstring_as_description(self):
        """Test that function docstring is used if no description provided."""
        registry = Registry()
        decorators = ValidatorDecorator(registry)

        @decorators.column_parser(name="documented")
        def parser_with_doc(column: pl.Expr) -> pl.Expr:
            """This is the docstring."""
            return column

        plugin = registry.column_parsers.get("documented")
        assert plugin.metadata.description == "This is the docstring."
