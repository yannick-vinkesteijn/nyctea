"""Package-level settings, in the shape of `pl.Config`.

Set globally, scope with a `with` block, or decorate a function.

    >>> import nyctea
    >>> nyctea.Config.set_streaming_row_threshold(0)  # doctest: +ELLIPSIS
    <class '...Config'>
    >>> with nyctea.Config(lazy=False):
    ...     pass
    >>> nyctea.Config.restore_defaults()  # doctest: +ELLIPSIS
    <class '...Config'>
"""

from collections.abc import Callable
from functools import wraps
from types import TracebackType
from typing import Any, ClassVar, Self

__all__ = ["Config"]

_DEFAULTS: dict[str, Any] = {
    "lazy": True,
    "streaming_row_threshold": 100_000,
}


class Config:
    """Nyctea's package-level settings.

    Usable three ways, like `pl.Config`: call the setters for a global change, use an
    instance as a context manager to scope one, or as a decorator to scope it to a
    function.
    """

    _state: ClassVar[dict[str, Any]] = dict(_DEFAULTS)

    def __init__(self, **options: Any) -> None:
        """Scope settings to a `with` block or a decorated function.

        Args:
            **options: Settings to apply for the duration. Names match the setters,
                so `lazy` and `streaming_row_threshold`.
        """
        self._options = options
        self._saved: dict[str, Any] | None = None

    def __enter__(self) -> Self:
        """Apply the scoped settings, remembering what to put back."""
        for key, value in self._options.items():
            Config._validate(key, value)
        self._saved = self.save()
        for key, value in self._options.items():
            Config._set(key, value)
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        """Restore whatever was in place before the block."""
        if self._saved is not None:
            self.load(self._saved)
            self._saved = None

    def __call__(self, func: Callable[..., Any]) -> Callable[..., Any]:
        """Scope the settings to one function."""

        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            with Config(**self._options):
                return func(*args, **kwargs)

        return wrapper

    @classmethod
    def _validate(cls, key: str, value: Any) -> None:
        """Reject an unknown setting name or invalid value."""
        if key not in _DEFAULTS:
            known = ", ".join(sorted(_DEFAULTS))
            raise ValueError(f"Unknown nyctea setting '{key}'. Known settings: {known}")
        if key == "streaming_row_threshold" and value < 0:
            raise ValueError(f"streaming_row_threshold must be greater than or equal to 0, got {value}")

    @classmethod
    def _set(cls, key: str, value: Any) -> None:
        """Set one setting after validating it."""
        cls._validate(key, value)
        cls._state[key] = value

    @classmethod
    def set_lazy(cls, value: bool) -> type["Config"]:
        """Return LazyFrames from `validate()` rather than collecting.

        Args:
            value: True to stay lazy.

        Returns:
            The class, so calls chain.
        """
        cls._set("lazy", value)
        return cls

    @classmethod
    def set_streaming_row_threshold(cls, value: int) -> type["Config"]:
        """Row count at or above which internal aggregates use the streaming engine.

        Args:
            value: Row count. 0 means always stream.

        Returns:
            The class, so calls chain.

        Raises:
            ValueError: If the value is negative, which would invert the choice.
        """
        cls._set("streaming_row_threshold", value)
        return cls

    @classmethod
    def lazy(cls) -> bool:
        """The configured lazy setting."""
        return bool(cls._state["lazy"])

    @classmethod
    def streaming_row_threshold(cls) -> int:
        """The configured streaming threshold."""
        return int(cls._state["streaming_row_threshold"])

    @classmethod
    def save(cls) -> dict[str, Any]:
        """Snapshot the current settings.

        Returns:
            A copy that `load()` accepts.
        """
        return dict(cls._state)

    @classmethod
    def load(cls, state: dict[str, Any]) -> type["Config"]:
        """Restore a snapshot from `save()`.

        Args:
            state: The snapshot.

        Returns:
            The class, so calls chain.
        """
        cls._state = dict(state)
        return cls

    @classmethod
    def restore_defaults(cls) -> type["Config"]:
        """Put every setting back to its shipped default.

        Returns:
            The class, so calls chain.
        """
        cls._state = dict(_DEFAULTS)
        return cls
