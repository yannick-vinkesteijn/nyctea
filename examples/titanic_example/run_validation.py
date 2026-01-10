"""Script to run validation for the Titanic example and write outputs."""


import sys
from pathlib import Path

import polars as pl

project_root = Path(__file__).resolve().parents[2]
for path in (project_root / "src", project_root):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from nyctea.engine import ErrorReportConfig, validate
from nyctea.ingest import read_csv
from nyctea.schema.model import SchemaModel
from examples.titanic_example.functions import registry


def main() -> None:
    schema_path = project_root / "examples/titanic_example/schema.yaml"
    data_path = project_root / "examples/titanic_example/titanic_sample.csv"
    output_data = project_root / "examples/titanic_example/validated.parquet"
    output_errors = project_root / "examples/titanic_example/errors.parquet"

    schema = SchemaModel.from_yaml_file(schema_path)
    lf = read_csv(data_path, schema, lazy=True, typed=False)

    # Use summary mode for production - minimal overhead
    error_config = ErrorReportConfig(mode="summary")
    result = validate(lf, schema, registry, lazy=False, coerce_strategy="null_on_failure", error_report=error_config)
    data_df: pl.DataFrame = result.data  # type: ignore[assignment]
    errors_df: pl.DataFrame = result.errors

    data_df.write_parquet(output_data)
    errors_df.write_parquet(output_errors)

    print(f"Wrote validated data to {output_data} (rows={data_df.height})")
    print(f"Wrote errors to {output_errors} (rows={errors_df.height})")
    if errors_df.height:
        print(errors_df)


if __name__ == "__main__":
    main()
