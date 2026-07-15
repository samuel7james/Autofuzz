"""Unit tests for the protocol FSM sequence builder (Phase 5)."""

from __future__ import annotations

from autofuzz.protocol_fuzzing.fsm import FsmState, ProtocolFsm


def test_from_commands_builds_named_states() -> None:
    fsm = ProtocolFsm.from_commands(["USER a", "PASS b"])

    assert fsm.states == [
        FsmState(name="step-0", command="USER a"),
        FsmState(name="step-1", command="PASS b"),
    ]


def test_commands_returns_flat_command_list() -> None:
    fsm = ProtocolFsm.from_commands(["USER a", "PASS b", "QUIT"])

    assert fsm.commands() == ["USER a", "PASS b", "QUIT"]


def test_empty_fsm_has_no_commands() -> None:
    fsm = ProtocolFsm()

    assert fsm.commands() == []
