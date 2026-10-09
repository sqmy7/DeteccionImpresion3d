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
    ok: bool | None  # None: sent, the printer has not answered yet
    error: str | None
    sent_at: datetime
    monotonic: float
    claimed: bool = False  # already used to explain a state change
    logged: bool = False  # already written to the event log
    failure_logged: bool = False  # the failure that came after the order was written too


_commands: deque[SentCommand] = deque(maxlen=200)


def begin(base_url: str, action: str, requested_by: str | None) -> SentCommand:
    """Notes the order BEFORE it is sent. The printer pauses within a second but only answers the request when
    its PAUSE macro ends (about 9 s on the Creality Hi), and a resume answers 45 to 65 s later: noted when the
    answer came, the order would be logged after the state change it caused, which then looked external."""
    command = SentCommand(
        base_url=base_url,
        action=action,
        requested_by=requested_by,
        ok=None,
        error=None,
        sent_at=datetime.now(timezone.utc),
        monotonic=time.monotonic(),
    )
    _commands.append(command)
    return command


def finish(command: SentCommand, ok: bool, error: str | None = None) -> None:
    command.ok = ok
    command.error = error


def record(base_url: str, action: str, requested_by: str | None, ok: bool, error: str | None = None) -> None:
    """An order already answered (used when the answer is all there is to note)."""
    finish(begin(base_url, action, requested_by), ok, error)


@dataclass
class RecentCommand:
    action: str
    ok: bool | None
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


def take_failed_unreported(base_url: str) -> list[SentCommand]:
    """Orders already written to the event log that failed afterwards: the log is append-only, so the failure
    is a second entry."""
    now = time.monotonic()
    failed = [
        command
        for command in _commands
        if command.base_url == base_url
        and command.logged
        and command.ok is False
        and not command.failure_logged
        and now - command.monotonic <= _KEEP_SECONDS
    ]
    for command in failed:
        command.failure_logged = True
    return failed


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
