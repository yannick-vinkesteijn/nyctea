"""Tests for decorator-based validator registration."""

import polars as pl
import pytest

from nyctea import Registry, SchemaModel, register_builtins
from nyctea.exceptions import RegistrationError
from nyctea.validators.catalogue import CATALOGUE
from nyctea.validators.decorators import checker, frame_checker, frame_parser, parser


class TestColumnParserDecorator:
    """Tests for column_parser decorator."""

    def test_basic_registration(self):
        """Test basic parser registration via decorator."""
        registry = Registry()

        @parser(registry=registry, name="test_trim")
        def trim(column: pl.Expr) -> pl.Expr:
            return column.str.strip_chars()

        # Verify validator was registered
        assert "test_trim" in registry.column_parsers.list_names()

        # Verify we can retrieve it
        validator = registry.column_parsers.get("test_trim")
        assert validator.name == "test_trim"

    def test_with_metadata(self):
        """Test parser with full metadata."""
        registry = Registry()

        @parser(
            registry=registry,
            name="uppercase",
            description="Convert to uppercase",
            version="2.0.0",
            tags=["string", "formatting"],
            author="Test Author",
        )
        def to_upper(column: pl.Expr) -> pl.Expr:
            return column.str.to_uppercase()

        validator = registry.column_parsers.get("uppercase")
        assert validator.metadata.name == "uppercase"
        assert validator.metadata.description == "Convert to uppercase"
        assert validator.metadata.version == "2.0.0"
        assert "string" in validator.metadata.tags
        assert "formatting" in validator.metadata.tags
        assert validator.metadata.author == "Test Author"

    def test_functional_usage(self):
        """Test that decorated function still works as a function."""
        registry = Registry()

        @parser(registry=registry, name="double")
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

        @parser(registry=registry, name="custom_trim")
        def trim(column: pl.Expr) -> pl.Expr:
            return column.str.strip_chars()

        schema = SchemaModel.from_dict(
            {
                "columns": {
                    "text": {
                        "dtype": "Utf8",
                        "parsers": [{"name": "custom_trim"}],
                        "nullable": False,
                    },
                }
            }
        )

        df = pl.DataFrame({"text": ["  hello  ", "  world  "]})
        result = schema.validate(df, registry)
        assert result.data.collect()["text"].to_list() == ["hello", "world"]


class TestColumnCheckDecorator:
    """Tests for column_check decorator."""

    def test_basic_registration(self):
        """Test basic check registration via decorator."""
        registry = Registry()

        @checker(registry=registry, name="test_positive")
        def is_positive(column: pl.Expr) -> pl.Expr:
            return column > 0

        # Verify validator was registered
        assert "test_positive" in registry.column_checks.list_names()

        # Verify we can retrieve it
        validator = registry.column_checks.get("test_positive")
        assert validator.name == "test_positive"

    def test_with_metadata(self):
        """Test check with full metadata."""
        registry = Registry()

        @checker(
            registry=registry,
            name="not_empty",
            description="Check string not empty",
            version="1.5.0",
            tags=["string", "validation"],
        )
        def check_not_empty(column: pl.Expr) -> pl.Expr:
            return column.str.len_chars() > 0

        validator = registry.column_checks.get("not_empty")
        assert validator.metadata.name == "not_empty"
        assert validator.metadata.description == "Check string not empty"
        assert validator.metadata.version == "1.5.0"
        assert "string" in validator.metadata.tags

    def test_integration_with_schema(self):
        """Test decorator-registered check works in schema validation."""
        registry = Registry()
        register_builtins(registry)

        @checker(registry=registry, name="positive", tags=["numeric"])
        def is_positive(column: pl.Expr) -> pl.Expr:
            return column > 0

        schema = SchemaModel.from_dict(
            {
                "columns": {
                    "value": {
                        "dtype": "Int64",
                        "parsers": [{"name": "to_int"}],
                        "checks": [{"name": "positive"}],
                        "nullable": False,
                        "on_failure": "ignore",
                    },
                }
            }
        )

        # Test with valid data
        df_good = pl.DataFrame({"value": ["1", "2", "3"]})
        result_good = schema.validate(df_good, registry)
        assert result_good.report.rows_valid == 3

        # Test with invalid data
        df_bad = pl.DataFrame({"value": ["1", "-2", "3"]})
        result_bad = schema.validate(df_bad, registry)
        assert len(result_bad.errors) > 0


class TestDecoratorEdgeCases:
    """Tests for edge cases and error handling."""

    def test_missing_input_parameter_is_rejected(self):
        registry = Registry()

        with pytest.raises(ValueError, match="first positional parameter"):

            @checker(registry=registry, name="broken")
            def broken() -> pl.Expr:
                return pl.lit(True)

    def test_keyword_only_input_is_rejected(self):
        registry = Registry()

        with pytest.raises(ValueError, match="first positional parameter"):

            @checker(registry=registry, name="broken")
            def broken(*, column: pl.Expr) -> pl.Expr:
                return column.is_not_null()

    def test_duplicate_registration_raises_error(self):
        """Test that registering duplicate name raises error."""
        registry = Registry()

        @parser(registry=registry, name="duplicate")
        def first(column: pl.Expr) -> pl.Expr:
            return column

        with pytest.raises(RegistrationError):

            @parser(registry=registry, name="duplicate")
            def second(column: pl.Expr) -> pl.Expr:
                return column

    def test_docstring_as_description(self):
        """Test that function docstring is used if no description provided."""
        registry = Registry()

        @parser(registry=registry, name="documented")
        def parser_with_doc(column: pl.Expr) -> pl.Expr:
            """This is the docstring."""
            return column

        validator = registry.column_parsers.get("documented")
        assert validator.metadata.description == "This is the docstring."


@pytest.fixture
def clean_catalogue():
    """Restore CATALOGUE after a test declares into it with no registry."""
    before = list(CATALOGUE)
    yield
    CATALOGUE[:] = before


class TestBareForm:
    """`@checker`/`@parser`/`@frame_checker`/`@frame_parser` without `()`."""

    def test_checker_infers_name_from_function(self):
        registry = Registry()

        @checker(registry=registry)
        def positive(column: pl.Expr) -> pl.Expr:
            return column > 0

        assert "positive" in registry.column_checks.list_names()

    def test_parser_infers_name_from_function(self):
        registry = Registry()

        @parser(registry=registry)
        def trim(column: pl.Expr) -> pl.Expr:
            return column.str.strip_chars()

        assert "trim" in registry.column_parsers.list_names()

    def test_frame_checker_infers_name_from_function(self):
        registry = Registry()

        @frame_checker(registry=registry)
        def min_rows(frame: pl.LazyFrame) -> pl.LazyFrame:
            return frame

        assert "min_rows" in registry.frame_checks.list_names()

    def test_frame_parser_infers_name_from_function(self):
        registry = Registry()

        @frame_parser(registry=registry)
        def add_total(frame: pl.LazyFrame) -> pl.LazyFrame:
            return frame

        assert "add_total" in registry.frame_parsers.list_names()

    def test_explicit_name_overrides_inference(self):
        registry = Registry()

        @checker(name="custom_name", registry=registry)
        def positive(column: pl.Expr) -> pl.Expr:
            return column > 0

        assert "custom_name" in registry.column_checks.list_names()
        assert "positive" not in registry.column_checks.list_names()

    def test_bare_form_still_callable_directly(self):
        registry = Registry()

        @checker(registry=registry)
        def above_zero(column: pl.Expr) -> pl.Expr:
            return column > 0

        df = pl.DataFrame({"x": [1, -1, 2]})
        result = df.select(above_zero(pl.col("x")))
        assert result["x"].to_list() == [True, False, True]

    def test_bare_no_registry_declares_into_catalogue(self, clean_catalogue):
        """No `registry=` at all: declared into `CATALOGUE`, same as the built-ins."""
        before = len(CATALOGUE)

        @checker
        def catalogued_check(column: pl.Expr) -> pl.Expr:
            return column > 0

        assert len(CATALOGUE) == before + 1
        assert CATALOGUE[-1].name == "catalogued_check"

    def test_catalogued_check_reaches_register_builtins(self, clean_catalogue):
        @checker
        def another_catalogued_check(column: pl.Expr) -> pl.Expr:
            return column > 0

        registry = Registry()
        register_builtins(registry)
        assert "another_catalogued_check" in registry.column_checks.list_names()
