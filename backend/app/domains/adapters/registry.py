"""
B.4.1 — Adapter Registry.

Minimal registry for adapter discovery by channel_code.
No DI container, no production config — designed for testability.
"""
from app.domains.orchestrator.contracts import AdapterContract


_registry: dict[str, AdapterContract] = {}


def register_adapter(adapter: AdapterContract) -> None:
    """Register an adapter by its channel_code.

    Raises ValueError if channel_code already registered and adapter differs.
    """
    code = adapter.channel_code
    if code in _registry and _registry[code] is not adapter:
        raise ValueError(
            f"Adapter for channel_code '{code}' already registered: "
            f"{_registry[code].adapter_name}"
        )
    _registry[code] = adapter


def get_adapter(channel_code: str) -> AdapterContract | None:
    """Get registered adapter by channel_code, or None."""
    return _registry.get(channel_code)


def list_adapters() -> dict[str, str]:
    """List all registered adapters as {channel_code: adapter_name}."""
    return {code: a.adapter_name for code, a in _registry.items()}


def clear_registry() -> None:
    """Clear all registered adapters (for test isolation)."""
    _registry.clear()
