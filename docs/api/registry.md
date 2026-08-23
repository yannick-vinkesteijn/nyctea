# Validator Registry

The registry holds the parsers and checks a schema resolves by name.

## Registry

`Registry` is the public entry point. It groups four `ValidatorRegistry` instances,
one per validator kind.

::: nyctea.validators.registry.Registry

## ValidatorRegistry

::: nyctea.validators.registry.ValidatorRegistry

## Decorators

::: nyctea.validators.decorators.ValidatorDecorator

---

## Legacy: FunctionRegistry

`nyctea.functions.registry` is the pre-`Registry` system. It is retained for compatibility and
scheduled for removal. New code should use `Registry` above.

### FunctionRegistry

::: nyctea.functions.registry.FunctionRegistry

### Wrappers

#### ColumnFunctionWrapper

::: nyctea.functions.registry.ColumnFunctionWrapper

#### FrameFunctionWrapper

::: nyctea.functions.registry.FrameFunctionWrapper

#### DecoratorAdapter

::: nyctea.functions.registry.DecoratorAdapter

### Signature validation

#### SignatureValidator

::: nyctea.functions.registry.SignatureValidator

### Exceptions

#### RegistryError

::: nyctea.functions.registry.RegistryError

#### ColumnPurityError

::: nyctea.functions.registry.ColumnPurityError

#### FrameShapeError

::: nyctea.functions.registry.FrameShapeError
