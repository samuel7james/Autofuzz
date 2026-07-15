"""Unit tests for ScanSession lifecycle and persistence (Phase 3)."""

from __future__ import annotations

from pathlib import Path

import pytest

from autofuzz.core.config import ScanProfile
from autofuzz.core.errors import EngineError
from autofuzz.core.scan import ScanSession, ScanState


def _profile() -> ScanProfile:
    return ScanProfile(name="test-profile", engine="web", authorized=True)


def test_new_session_starts_in_created_state() -> None:
    session = ScanSession.create(_profile())
    assert session.state == ScanState.CREATED
    assert session.id


def test_valid_lifecycle_transitions() -> None:
    session = ScanSession.create(_profile())
    session.start()
    assert session.state == ScanState.RUNNING
    session.pause()
    assert session.state == ScanState.PAUSED
    session.start()
    assert session.state == ScanState.RUNNING
    session.complete()
    assert session.state == ScanState.COMPLETED


def test_invalid_transition_raises() -> None:
    session = ScanSession.create(_profile())
    with pytest.raises(EngineError):
        session.complete()  # cannot complete a session that never started


def test_fail_records_error_message() -> None:
    session = ScanSession.create(_profile())
    session.start()
    session.fail("target unreachable")
    assert session.state == ScanState.FAILED
    assert session.error == "target unreachable"


def test_save_and_load_roundtrip(tmp_path: Path) -> None:
    session = ScanSession.create(_profile())
    session.start()
    session.progress["pages_crawled"] = 42
    path = session.save(tmp_path)

    loaded = ScanSession.load(path)

    assert loaded.id == session.id
    assert loaded.state == ScanState.RUNNING
    assert loaded.progress == {"pages_crawled": 42}
    assert loaded.profile.name == "test-profile"


def test_resume_moves_paused_session_back_to_running(tmp_path: Path) -> None:
    session = ScanSession.create(_profile())
    session.start()
    session.pause()
    session.save(tmp_path)

    resumed = ScanSession.resume(tmp_path, session.id)

    assert resumed.state == ScanState.RUNNING


def test_load_missing_session_raises(tmp_path: Path) -> None:
    with pytest.raises(EngineError):
        ScanSession.load(tmp_path / "does-not-exist.json")
