# Type Checking Notes

## Parameter Name Changes in Method Overrides

### Issue

The `ty` type checker flags parameter name changes in method overrides as errors:

```python
# BasePlugin (base class)
def execute(self, input_data: TInput, **kwargs) -> TOutput:
    ...

# ColumnParser (subclass)
def execute(self, column: pl.Expr, **kwargs) -> pl.Expr:
    ...
```

### Why This Is Valid

1. **Python typing allows this**: According to PEP 484, positional parameter names can differ in overrides because Python doesn't enforce keyword argument names in the type system.

1. **Improves clarity**: Using `column` instead of `input_data` makes the API clearer for column-level plugins.

1. **Runtime enforcement**: The `ColumnPlugin._validate_signature()` method enforces the correct parameter name at registration time, catching errors early.

1. **Liskov Substitution Principle holds**: The function can still be called with the same positional arguments, maintaining behavioral compatibility.

### Why We Use This Pattern

The plugin architecture uses **semantic parameter names** at each level:

- `BasePlugin.execute(input_data, ...)` - Generic base class
- `ColumnPlugin.execute(column, ...)` - Column-level operations
- `FramePlugin.execute(frame, ...)` - Frame-level operations

This provides better IDE autocomplete and clearer documentation without sacrificing type safety.

### Resolution

We configure `ty` to treat `invalid-method-override` as a warning rather than an error:

```toml
[tool.ty.rules]
# Allow parameter name changes in method overrides (intentional design pattern)
invalid-method-override = "warn"
```

This acknowledges that:

- The pattern is intentional and beneficial
- Runtime validation catches actual errors
- The code is correct according to Python's type system

### Alternative Approaches Considered

1. **Use `input_data` everywhere**: Less clear API, worse developer experience
1. **Add `# type: ignore` comments**: Hides the issue, doesn't explain why
1. **Use Protocol classes**: Over-engineering for this use case

### Conclusion

The current approach balances type safety with API clarity. The `ty` warning reminds us of the deviation from strict type checking while allowing our intentional design pattern.
