"""Channel Adapters domain — B.4.

Channel-specific adapter implementations for the Orchestrator.
Each adapter implements AdapterContract for its channel (KSO, Android TV, etc.).
"""
from app.domains.adapters.mock_adapter import MockAdapter
from app.domains.adapters.registry import (
    register_adapter,
    get_adapter,
    list_adapters,
    clear_registry,
)

__all__ = [
    "MockAdapter",
    "register_adapter",
    "get_adapter",
    "list_adapters",
    "clear_registry",
]
