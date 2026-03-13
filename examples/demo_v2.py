"""Demo: v0.2.0 pipeline with dirty data.

Run with: uv run python examples/demo_v2.py
"""

import polars as pl

from nyctea import Registry, SchemaModel, register_builtins

# --- Schema: what clean data looks like ---
# on_failure="null" at schema level: failed casts/checks become null
# patient_id overrides to "raise" — must be clean
schema = SchemaModel.from_dict({
    "coerce": True,
    "on_failure": "null",
    "columns": {
        "patient_id": {
            "dtype": "Utf8",
            "synonyms": ["pid"],
            "parsers": [{"name": "strip"}],
            "nullable": False,
            "on_failure": "raise",
        },
        "age": {
            "dtype": "Int64",
            "synonyms": ["Age", "AGE"],
            "parsers": [{"name": "strip"}],
            "checks": [{"name": "between", "args": {"min": 0, "max": 120}}],
            "nullable": True,
        },
        "temperature": {
            "dtype": "Float64",
            "parsers": [{"name": "strip"}],
            "checks": [{"name": "between", "args": {"min": 35.0, "max": 42.0}}],
            "nullable": True,
        },
        "status": {
            "dtype": "Utf8",
            "parsers": [{"name": "strip"}, {"name": "lower"}],
            "checks": [{"name": "in_set", "args": {"values": ["active", "discharged", "deceased"]}}],
            "nullable": True,
        },
    },
})

# --- Dirty data: synonyms, wrong types, bad values, whitespace ---
dirty = pl.DataFrame({
    "pid":         ["  001", "002", "003 ", "004", "005", "006"],
    "AGE":         ["34",   "not_a_number", "150",  "29",  "-5",  "67"],
    "temperature": ["36.6", "abc",   "45.2", "37.1", "36.8", "38.0"],
    "status":      [" Active ", "DISCHARGED", "unknown", "active", "  Deceased", None],
})

print("=" * 60)
print("INPUT (dirty)")
print("=" * 60)
print(dirty)
print()

# --- Registry with built-in plugins ---
registry = Registry()
register_builtins(registry)

# --- Run validation: on_failure="null" lets bad casts become null ---
result = schema.validate(dirty, registry, lazy=False)

print("=" * 60)
print("OUTPUT (validated)")
print("=" * 60)
print(result.data)
print()

print("=" * 60)
print("ERRORS")
print("=" * 60)
print(result.errors)
print()

print("=" * 60)
print("REPORT")
print("=" * 60)
print(result.report.summary())
print()

# --- Strict mode: on_failure="raise" raises on coercion failure ---
print("=" * 60)
print("STRICT MODE (should raise)")
print("=" * 60)
strict_schema = SchemaModel.from_dict({
    "coerce": True,
    "on_failure": "raise",
    "columns": {
        "patient_id": {"dtype": "Utf8", "synonyms": ["pid"], "parsers": [{"name": "strip"}], "nullable": False},
        "age": {"dtype": "Int64", "synonyms": ["Age", "AGE"], "parsers": [{"name": "strip"}], "nullable": True},
        "temperature": {"dtype": "Float64", "parsers": [{"name": "strip"}], "nullable": True},
        "status": {"dtype": "Utf8", "parsers": [{"name": "strip"}, {"name": "lower"}], "nullable": True},
    },
})
try:
    strict_schema.validate(dirty, registry)
except Exception as e:
    print(f"{type(e).__name__}: {e}")
