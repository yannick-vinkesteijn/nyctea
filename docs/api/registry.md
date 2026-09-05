# Validator Registry

The registry holds the parsers and checks a schema resolves by name.

## Registry

`Registry` is the public entry point. It groups four `ValidatorRegistry` instances,
one per validator kind.

::: nyctea.validators.registry.Registry

## ValidatorRegistry

::: nyctea.validators.registry.ValidatorRegistry

## Decorators

::: nyctea.validators.decorators.checker

::: nyctea.validators.decorators.parser

::: nyctea.validators.decorators.frame_checker

::: nyctea.validators.decorators.frame_parser
