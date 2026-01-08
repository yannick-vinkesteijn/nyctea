"""CLI entry point for inspecting schemas."""

import argparse
import json
from pathlib import Path
from typing import Any

from nyctea.schema.loader import SchemaLoader
from nyctea.utils import get_logger

log = get_logger(__name__)


def load_schema(path: str) -> Any:
    """Load a schema from a JSON or YAML file.

    Args:
        path: Path to the schema file.

    Returns:
        SchemaModel: Loaded schema instance.

    Raises:
        SystemExit: If the extension is unsupported.
    """
    loader = SchemaLoader()
    suffix = Path(path).suffix.lower()
    if suffix == ".json":
        schema = loader.from_json_file(path)
    elif suffix in (".yaml", ".yml"):
        schema = loader.from_yaml_file(path)
    else:
        raise SystemExit(f"Unsupported schema extension: {suffix}")
    return schema


def main() -> None:
    """Parse arguments and display the loaded schema."""
    parser = argparse.ArgumentParser(description="Inspect a validation schema.")
    parser.add_argument("schema", help="Path to schema file (json|yaml)")
    args = parser.parse_args()

    schema = load_schema(args.schema)
    log.info("Loaded schema with %d columns", len(schema.columns))
    print(json.dumps(schema.model_dump(), indent=2))


if __name__ == "__main__":
    main()
