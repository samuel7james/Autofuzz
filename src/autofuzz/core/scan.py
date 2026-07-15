"""Scan lifecycle management: a state machine plus JSON persistence for resume.

Engine-agnostic: the same ``ScanSession`` tracks a long protocol fuzzing run
or a large web crawl, so ``autofuzz resume <scan-id>`` (Phase 7) works
identically for both.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

from autofuzz.core.config import ScanProfile
from autofuzz.core.errors import EngineError


class ScanState(str, Enum):
    CREATED = "created"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class ScanSession:
    """Tracks one scan's identity, profile, target, state, and progress for resume."""

    id: str
    profile: ScanProfile
    target: str = ""
    state: ScanState = ScanState.CREATED
    created_at: str = field(default_factory=_now)
    updated_at: str = field(default_factory=_now)
    progress: dict[str, Any] = field(default_factory=dict)
    error: str | None = None

    @classmethod
    def create(cls, profile: ScanProfile, target: str = "") -> ScanSession:
        return cls(id=uuid.uuid4().hex[:12], profile=profile, target=target)

    def _transition(self, new_state: ScanState, *, allowed_from: set[ScanState]) -> None:
        if self.state not in allowed_from:
            raise EngineError(
                f"Cannot move scan {self.id} from {self.state.value} to {new_state.value}"
            )
        self.state = new_state
        self.updated_at = _now()

    def start(self) -> None:
        """Move to RUNNING. Allowed from CREATED/PAUSED (normal start/resume) and
        from RUNNING/FAILED too - a session left RUNNING or FAILED usually means the
        process that owned it died or was killed mid-scan, and resuming that is
        exactly what `autofuzz resume` is for."""
        self._transition(
            ScanState.RUNNING,
            allowed_from={
                ScanState.CREATED,
                ScanState.PAUSED,
                ScanState.RUNNING,
                ScanState.FAILED,
            },
        )

    def pause(self) -> None:
        self._transition(ScanState.PAUSED, allowed_from={ScanState.RUNNING})

    def complete(self) -> None:
        self._transition(ScanState.COMPLETED, allowed_from={ScanState.RUNNING})

    def fail(self, error: str) -> None:
        self.error = error
        self._transition(
            ScanState.FAILED,
            allowed_from={ScanState.CREATED, ScanState.RUNNING, ScanState.PAUSED},
        )

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["profile"] = self.profile.model_dump(mode="json")
        data["state"] = self.state.value
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ScanSession:
        return cls(
            id=data["id"],
            profile=ScanProfile.model_validate(data["profile"]),
            target=data.get("target", ""),
            state=ScanState(data["state"]),
            created_at=data["created_at"],
            updated_at=data["updated_at"],
            progress=data.get("progress", {}),
            error=data.get("error"),
        )

    def save(self, directory: Path) -> Path:
        """Persist this session as ``<directory>/<id>.json``."""
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f"{self.id}.json"
        path.write_text(json.dumps(self.to_dict(), indent=2), encoding="utf-8")
        return path

    @classmethod
    def load(cls, path: Path) -> ScanSession:
        if not path.is_file():
            raise EngineError(f"Scan session not found: {path}")
        return cls.from_dict(json.loads(path.read_text(encoding="utf-8")))

    @classmethod
    def resume(cls, directory: Path, scan_id: str) -> ScanSession:
        """Load a session by id and move it back to RUNNING (from CREATED/PAUSED)."""
        session = cls.load(directory / f"{scan_id}.json")
        session.start()
        return session
