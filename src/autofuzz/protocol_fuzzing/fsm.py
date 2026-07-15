"""FSM-based sequence builder for protocol fuzzing.

Generalizes v1's hardcoded ``BASE_SEQUENCE``: a protocol interaction is
just an ordered list of states, each carrying one command. Adapters
provide a default sequence for their protocol; profiles can override it
later without touching adapter code.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class FsmState:
    """One step in a protocol sequence: a name (for logging) and the literal
    command text to send at this step."""

    name: str
    command: str


@dataclass
class ProtocolFsm:
    """An ordered sequence of states defining one full protocol interaction."""

    states: list[FsmState] = field(default_factory=list)

    def commands(self) -> list[str]:
        return [state.command for state in self.states]

    @classmethod
    def from_commands(cls, commands: list[str]) -> ProtocolFsm:
        """Build an FSM from a flat list of command strings, auto-naming each state."""
        return cls(
            states=[FsmState(name=f"step-{i}", command=cmd) for i, cmd in enumerate(commands)]
        )
