"""KSO UKM 4 State Adapter — state source abstraction.

Injectable source interface for reading terminal state.
Real UKM 4 integration is a future step.
"""

from dataclasses import dataclass
from typing import List, Optional, Protocol, runtime_checkable

from kso_state_adapter.state_model import KsoState, STATE_IDLE, STATE_UNKNOWN


# ══════════════════════════════════════════════════════════════════════
# Source protocol
# ══════════════════════════════════════════════════════════════════════

@runtime_checkable
class KsoStateSource(Protocol):
    """Injectable state source. Real UKM 4 integration will implement this."""

    def read_state(self) -> KsoState:
        """Read current terminal state. Must never raise."""
        ...


# ══════════════════════════════════════════════════════════════════════
# Static source
# ══════════════════════════════════════════════════════════════════════

class StaticStateSource:
    """Always returns the same state. For testing and manual override."""

    def __init__(self, state: str = STATE_UNKNOWN):
        if state not in (
            "idle", "transaction", "payment", "receipt",
            "service", "error", "maintenance", "offline", "unknown",
        ):
            raise ValueError(f"Invalid state: {state}")
        self._state = state

    def read_state(self) -> KsoState:
        return KsoState(state=self._state)


# ══════════════════════════════════════════════════════════════════════
# Sequence source
# ══════════════════════════════════════════════════════════════════════

class SequenceStateSource:
    """Returns states from a predefined sequence. For scenario testing."""

    def __init__(self, states: List[str]):
        if not states:
            raise ValueError("States list must not be empty")
        for s in states:
            if s not in (
                "idle", "transaction", "payment", "receipt",
                "service", "error", "maintenance", "offline", "unknown",
            ):
                raise ValueError(f"Invalid state in sequence: {s}")
        self._states = list(states)
        self._index = 0
        self.call_count = 0

    def read_state(self) -> KsoState:
        self.call_count += 1
        state = self._states[self._index]
        self._index = (self._index + 1) % len(self._states)
        return KsoState(state=state)


# ══════════════════════════════════════════════════════════════════════
# Erroring source
# ══════════════════════════════════════════════════════════════════════

class ErroringStateSource:
    """Simulates a broken source. Always raises. For error handling tests."""

    def __init__(self, exception: Optional[Exception] = None):
        self._exception = exception or RuntimeError("source unavailable")
        self.call_count = 0

    def read_state(self) -> KsoState:
        self.call_count += 1
        raise self._exception
