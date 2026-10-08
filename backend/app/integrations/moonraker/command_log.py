"""Print-control orders PrintWatch itself sent (pause/resume), remembered in memory for a few
minutes. The Moonraker listener only sees the printer change state; this is how it tells a pause
PrintWatch asked for from one made on the printer's screen or in Fluidd."""

import time
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone

_KEEP_SECONDS = 600


@dataclass
class SentCommand:
    base_url: str
    action: str
    requested_by: str | None
    ok: bool
    error: str | None
    sent_at: datetime
    monotonic: float
    claimed: bool = False  # already used to explain a state change
    logged: bool = False  # already written to the event log


_commands: deque[SentCommand] = deque(maxlen=200)


def record(base_url: str, action: str, requested_by: str | None, ok: bool, error: str | None = None) -> None:
    _commands.append(
        SentCommand(
            base_url=base_url,
            action=action,
            requested_by=requested_by,
            ok=ok,
            error=error,
            sent_at=datetime.now(timezone.utc),
            monotonic=time.monotonic(),
        )
    )


@dataclass
class RecentCommand:
    action: str
    ok: bool
    age_seconds: float


def recent(base_url: str, action: str, within_seconds: float) -> RecentCommand | None:
    """The newest order of this kind sent to this printer within the window, claimed or not,
    failed or not (a request that timed out may still have reached the printer)."""
    now = time.monotonic()
    for command in reversed(_commands):
        if now - command.monotonic > within_seconds:
            break
        if command.base_url == base_url and command.action == action:
            return RecentCommand(command.action, command.ok, now - command.monotonic)
    return None


def claim_recent(base_url: str, action: str, within_seconds: float) -> SentCommand | None:
    """The newest unclaimed order of this kind sent to this printer within the window, marked so
    one order explains at most one state change. Failed orders count too: a request that timed
    out may still have reached the printer."""
    now = time.monotonic()
    for command in reversed(_commands):
        if now - command.monotonic > within_seconds:
            break
        if command.base_url == base_url and command.action == action and not command.claimed:
            command.claimed = True
            return command
    return None


def take_unlogged(base_url: str) -> list[SentCommand]:
    now = time.monotonic()
    pending = [
        command
        for command in _commands
        if command.base_url == base_url and not command.logged and now - command.monotonic <= _KEEP_SECONDS
    ]
    for command in pending:
        command.logged = True
    return pending
