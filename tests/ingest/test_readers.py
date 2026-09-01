"""Tests for nyctea.ingest.readers: read_csv, read_parquet, and _to_dtype."""

import polars as pl
import pytest

from nyctea.ingest.readers import _to_dtype, read_csv, read_parquet
from nyctea.schema.model import SchemaModel


@pytest.fixture
def schema():
    return SchemaModel.from_dict(
        {
            "lazy": False,
            "columns": {
                "passenger_id": {
                    "dtype": "Int64",
                    "nullable": False,
                    "synonyms": ["PassengerId"],
                },
                "name": {
                    "dtype": "Utf8",
                    "nullable": False,
                },
            },
        }
    )


def test_to_dtype_accepts_datatype_instance():
    assert _to_dtype(pl.Int64()) == pl.Int64


def test_to_dtype_accepts_valid_string():
    assert _to_dtype("Utf8") == pl.Utf8


def test_to_dtype_rejects_unknown_string():
    with pytest.raises(ValueError, match="Unknown dtype string"):
        _to_dtype("NotARealDtype")


def test_to_dtype_rejects_unsupported_spec_type():
    with pytest.raises(ValueError, match="Unsupported dtype specification"):
        _to_dtype(123)


def test_read_csv_untyped_reads_all_columns_as_utf8(tmp_path, schema):
    path = tmp_path / "data.csv"
    path.write_text("passenger_id,name\n1,Alice\n2,Bob\n")

    df = read_csv(path, schema, lazy=False)

    assert df.schema["passenger_id"] == pl.Utf8
    assert df.schema["name"] == pl.Utf8


def test_read_csv_typed_applies_declared_dtypes(tmp_path, schema):
    path = tmp_path / "data.csv"
    path.write_text("passenger_id,name\n1,Alice\n2,Bob\n")

    df = read_csv(path, schema, lazy=False, typed=True)

    assert df.schema["passenger_id"] == pl.Int64
    assert df.schema["name"] == pl.Utf8


def test_read_csv_typed_matches_synonym_column_names(tmp_path, schema):
    path = tmp_path / "data.csv"
    path.write_text("PassengerId,name\n1,Alice\n2,Bob\n")

    df = read_csv(path, schema, lazy=False, typed=True)

    assert df.schema["PassengerId"] == pl.Int64


def test_read_csv_typed_lazy_returns_lazyframe(tmp_path, schema):
    path = tmp_path / "data.csv"
    path.write_text("passenger_id,name\n1,Alice\n")

    result = read_csv(path, schema, lazy=True, typed=True)

    assert isinstance(result, pl.LazyFrame)


def test_read_csv_lazy_returns_lazyframe(tmp_path, schema):
    path = tmp_path / "data.csv"
    path.write_text("passenger_id,name\n1,Alice\n")

    result = read_csv(path, schema, lazy=True)

    assert isinstance(result, pl.LazyFrame)


def test_read_parquet_single_path(tmp_path, schema):
    path = tmp_path / "data.parquet"
    pl.DataFrame({"passenger_id": [1, 2], "name": ["Alice", "Bob"]}).write_parquet(path)

    df = read_parquet(path, schema, lazy=False)

    assert df.height == 2
    assert isinstance(df, pl.DataFrame)


def test_read_parquet_lazy_returns_lazyframe(tmp_path, schema):
    path = tmp_path / "data.parquet"
    pl.DataFrame({"passenger_id": [1], "name": ["Alice"]}).write_parquet(path)

    result = read_parquet(path, schema, lazy=True)

    assert isinstance(result, pl.LazyFrame)


def test_read_parquet_list_of_paths(tmp_path, schema):
    path_a = tmp_path / "a.parquet"
    path_b = tmp_path / "b.parquet"
    pl.DataFrame({"passenger_id": [1], "name": ["Alice"]}).write_parquet(path_a)
    pl.DataFrame({"passenger_id": [2], "name": ["Bob"]}).write_parquet(path_b)

    df = read_parquet([path_a, path_b], schema, lazy=False)

    assert df.height == 2
