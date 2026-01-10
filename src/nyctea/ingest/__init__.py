"""Data ingestion package for reading CSV and Parquet files."""

from nyctea.ingest.readers import read_csv, read_parquet

__all__ = ["read_csv", "read_parquet"]
