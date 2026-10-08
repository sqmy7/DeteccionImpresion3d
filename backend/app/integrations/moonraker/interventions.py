"""Bitácora de intervenciones: which changes on the printer were interventions, and who made them.

The Moonraker listener hands over every change of a watched field (heater targets, speed and flow
factors, fans, Z offset, excluded objects) and every print-state change it could not attribute on
the spot. InterventionTracker then looks for evidence, in this order:

1. console: a G-code command that explains the change in Moonraker's console log
   (/server/gcode_store, polled every few seconds). Fluidd and Mainsail send their sliders,
   babystep buttons, object exclusion and console input this way.
2. gcode_file: a line of the file being printed, or of a macro it calls, that explains the change,
   found at the byte offsets Klipper was reading when the change appeared.
3. external: no evidence. The printer's screen, Fluidd's pause/resume buttons (they use an API
   that leaves no trace in the console log) or another application; which one cannot be known.

Fan changes programmed in the file are not logged: slicers switch the fan constantly and the
telemetry series already has the curve. Unexplained fan changes are logged only when the file
could be checked, since without it most of them would be false "external" entries.

Everything here only reads from the printer (GET requests)."""

import asyncio
import logging
import math
import random
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any
from urllib.parse import quote

import httpx

from app.core.config import settings
from app.integrations.moonraker.gcode_effects import (
    Effect,
    FileCommand,
    FileIndex,
    GcodeScanner,
    explains,
    line_effects,
    macros_from_config,
)
from app.services.printer_events import EventOrigin

logger = logging.getLogger(__name__)

_CONSOLE_POLL_SECONDS = 2.0
_CONSOLE_FETCH = 100
_CONSOLE_KEEP_SECONDS = 120.0
# A change waits this long for its console command to show up (two polls plus margin).
_CONSOLE_WAIT_SECONDS = 5.0
# A console command explains changes seen up to this long before or after it was first seen.
_CONSOLE_MATCH_SECONDS = 20.0
# A change waits at most this long for the file being printed to be indexed.
_FILE_WAIT_SECONDS = 180.0
_FILE_POSITION_TOLERANCE = 256
# Indexing reads the file at no more than this rate so it never competes with the print for the
# printer's network and CPU, and stops after this many bytes.
_SCAN_BYTES_PER_SECOND = 1_000_000
_SCAN_MAX_BYTES = 200 * 1024 * 1024
_HTTP_TIMEOUT_SECONDS = 10

# Watched fields whose changes need attribution: (object or object-name prefix, field) -> event.
_ATTRIBUTED_FIELDS: dict[tuple[str, str], str] = {
    ("extruder", "target"): "target_changed",
    ("heater_bed", "target"): "target_changed",
    ("heater_generic ", "target"): "target_changed",
    ("temperature_fan ", "target"): "target_changed",
    ("gcode_move", "speed_factor"): "speed_factor_changed",
    ("gcode_move", "extrude_factor"): "flow_factor_changed",
    ("fan", "speed"): "fan_changed",
    ("fan_generic ", "speed"): "fan_changed",
}
# Changes the printer itself makes: logged right away with origin "printer".
_PRINTER_FIELDS: dict[tuple[str, str], str] = {
    ("webhooks", "state"): "klippy_state_changed",
    ("filament_switch_sensor ", "filament_detected"): "filament_sensor_changed",
    ("filament_motion_sensor ", "filament_detected"): "filament_sensor_changed",
}


@dataclass(frozen=True)
class FieldChange:
    event_type: str
    field: str
    before: Any
    after: Any
    needs_attribution: bool


@dataclass
class DetectedChange:
    event_type: str
    field: str
    before: Any
    after: Any
    observed_at: datetime
    observed_monotonic: float
    klipper_eventtime: float | None
    filename: str | None
    file_position_before: int | None
    file_position_after: int | None
    phase: str
    job_id: int | None
    detail: dict = field(default_factory=dict)

    @property
    def is_fan(self) -> bool:
        return self.event_type == "fan_changed"


@dataclass
class ConsoleCommand:
    text: str
    printer_time: float | None
    seen_monotonic: float
    effects: list[Effect]
    claimed: set[str] = field(default_factory=set)  # fields this command already explained


@dataclass
class Decision:
    record: bool
    origin: EventOrigin | None = None
    detail: dict = field(default_factory=dict)


def _lookup(table: dict[tuple[str, str], str], name: str, key: str) -> str | None:
    for (object_name, field_name), event_type in table.items():
        if field_name == key and (name == object_name or (object_name.endswith(" ") and name.startswith(object_name))):
            return event_type
    return None


def _z(vector) -> float | None:
    if isinstance(vector, (list, tuple)) and len(vector) > 2 and isinstance(vector[2], (int, float)):
        return vector[2]
    return None


def detect_changes(previous: dict, patch: dict) -> list[FieldChange]:
    """Watched fields that a status patch changes, compared with the merged status before it.
    A field seen for the first time has no "before" and is not a change."""
    changes = []
    for name, values in patch.items():
        if not isinstance(values, dict):
            continue
        old_values = previous.get(name) or {}
        for key, new in values.items():
            if key not in old_values or old_values[key] == new:
                continue
            old = old_values[key]
            if name == "gcode_move" and key == "homing_origin":
                if _z(old) != _z(new):
                    changes.append(FieldChange("z_offset_changed", "gcode_move.homing_origin[2]", _z(old), _z(new), True))
                continue
            if name == "exclude_object" and key == "excluded_objects":
                for excluded in new or []:
                    if excluded not in (old or []):
                        changes.append(FieldChange("object_excluded", "exclude_object.excluded_objects", None, excluded, True))
                continue
            if event_type := _lookup(_ATTRIBUTED_FIELDS, name, key):
                changes.append(FieldChange(event_type, f"{name}.{key}", old, new, True))
            elif event_type := _lookup(_PRINTER_FIELDS, name, key):
                changes.append(FieldChange(event_type, f"{name}.{key}", old, new, False))
    return changes


def print_phase(state: str | None, layer: int | None, progress: float | None, has_job: bool) -> str:
    """Where in the print a change happened; start and end are the file's (and its macros') own
    sequences, where programmed changes are expected."""
    if not has_job or state not in ("printing", "paused"):
        return "idle"
    if state == "paused":
        return "paused"
    if not layer:
        return "start"
    if progress is not None and progress >= 0.995:
        return "end"
    return "printing"


def _iso(printer_time) -> str | None:
    if not isinstance(printer_time, (int, float)):
        return None
    return datetime.fromtimestamp(printer_time, timezone.utc).isoformat()


def _round(value: float | None) -> float | None:
    return None if value is None else round(value, 3)


class ClockOffset:
    """Printer clock minus ours, from the HTTP Date header of the printer's answers. Date has
    whole seconds, so each answer only bounds the offset to a 1 s interval; intersecting the
    intervals of many answers, taken at different fractions of a second, narrows it down."""

    def __init__(self) -> None:
        self.low: float | None = None
        self.high: float | None = None

    def update(self, date_header: str | None, sent: float, received: float) -> None:
        try:
            printer_now = parsedate_to_datetime(date_header).timestamp()
        except (TypeError, ValueError, IndexError):
            return
        middle = (sent + received) / 2
        low, high = printer_now - middle, printer_now + 1 - middle
        if self.low is None or max(self.low, low) > min(self.high, high):
            # First answer, or the printer's clock jumped (NTP sync): start over.
            self.low, self.high = low, high
        else:
            self.low, self.high = max(self.low, low), min(self.high, high)

    @property
    def seconds(self) -> float | None:
        return None if self.low is None else (self.low + self.high) / 2

    def to_local(self, printer_time) -> datetime | None:
        if not isinstance(printer_time, (int, float)) or self.seconds is None:
            return None
        return datetime.fromtimestamp(printer_time - self.seconds, timezone.utc)


def _console_match(change: DetectedChange, console: list[ConsoleCommand]) -> ConsoleCommand | None:
    for command in reversed(console):
        if change.field in command.claimed:
            continue
        if abs(command.seen_monotonic - change.observed_monotonic) > _CONSOLE_MATCH_SECONDS:
            continue
        if any(explains(effect, change.field, change.after) for effect in command.effects):
            return command
    return None


def _file_match(change: DetectedChange, file_index: FileIndex | None) -> FileCommand | None:
    if file_index is None or change.file_position_after is None or change.filename != file_index.filename:
        return None
    start = change.file_position_after
    if change.file_position_before is not None and change.file_position_before <= change.file_position_after:
        start = change.file_position_before
    return file_index.find(
        change.field,
        change.after,
        max(0, start - _FILE_POSITION_TOLERANCE),
        change.file_position_after + _FILE_POSITION_TOLERANCE,
    )


def classify(
    change: DetectedChange,
    console: list[ConsoleCommand],
    file_index: FileIndex | None,
    file_scan_running: bool,
    now: float,
) -> Decision | None:
    """The origin of a change given the evidence so far, or None to wait for more."""
    command = _console_match(change, console)
    if command is not None:
        command.claimed.add(change.field)
        return Decision(True, EventOrigin.CONSOLE, {"command": command.text, "printer_time": _iso(command.printer_time)})

    file_command = _file_match(change, file_index)
    if file_command is not None:
        detail = {"line": file_command.line, "offset": file_command.offset}
        if file_command.via:
            detail["via_macro"] = file_command.via
        return Decision(not change.is_fan, EventOrigin.GCODE_FILE, detail)

    age = now - change.observed_monotonic
    if age < _CONSOLE_WAIT_SECONDS:
        return None
    file_checked = (
        file_index is not None
        and file_index.filename == change.filename
        and file_index.covers(change.file_position_after)
    )
    if file_scan_running and not file_checked and change.file_position_after is not None and age < _FILE_WAIT_SECONDS:
        return None
    if change.is_fan and not file_checked:
        return Decision(False)
    return Decision(True, EventOrigin.EXTERNAL, {"file_checked": file_checked})


class InterventionTracker:
    """One per Moonraker connection: polls the console log, indexes the file being printed and
    writes each pending change to the event log once its origin is decided. `state` is the
    listener's live printer state; `record(event_type, origin, **kwargs)` appends an event."""

    def __init__(self, base_url: str, state, record) -> None:
        self._base_url = base_url
        self._state = state
        self._record = record
        self._pending: list[DetectedChange] = []
        self._console: list[ConsoleCommand] = []
        self._console_cursor: tuple | None = None
        self.clock = ClockOffset()
        self._macros: dict[str, str] | None = None
        self._file_index: FileIndex | None = None
        self._scan_filename: str | None = None
        self._scan_task: asyncio.Task | None = None
        self._http = httpx.AsyncClient(timeout=_HTTP_TIMEOUT_SECONDS)

    def add(self, change: DetectedChange) -> None:
        self._pending.append(change)

    def want_file(self, filename: str | None) -> None:
        """Index the file being printed, once per file, in the background."""
        if not settings.gcode_scan_enabled or not filename or filename == self._scan_filename:
            return
        self._scan_filename = filename
        self._file_index = None
        if self._scan_task is not None:
            self._scan_task.cancel()
        self._scan_task = asyncio.create_task(self._scan_file(filename))

    @property
    def file_scan_running(self) -> bool:
        return self._scan_task is not None and not self._scan_task.done()

    async def run(self) -> None:
        await self._load_macros()
        while True:
            # Jittered, so the polls (and the Date headers ClockOffset learns from) land on
            # different fractions of a second.
            await asyncio.sleep(_CONSOLE_POLL_SECONDS * random.uniform(0.75, 1.25))
            await self._poll_console()
            await self._resolve(force=False)

    async def close(self) -> None:
        """The connection is ending: decide what is still pending with the evidence at hand."""
        if self._scan_task is not None:
            self._scan_task.cancel()
        try:
            await self._resolve(force=True)
        except Exception:
            logger.warning("Could not log the pending changes", exc_info=True)
        await self._http.aclose()

    async def _load_macros(self) -> None:
        try:
            response = await self._http.get(f"{self._base_url}/printer/objects/query", params={"configfile": "config"})
            response.raise_for_status()
            config = response.json()["result"]["status"]["configfile"]["config"]
            self._macros = macros_from_config(config)
        except (httpx.HTTPError, ValueError, KeyError, TypeError):
            logger.warning("Could not read the printer's macros; changes made inside macros won't be traced")
            self._macros = {}

    def _new_console_entries(self, entries: list[dict]) -> list[dict]:
        """Entries after the newest one seen in the previous poll. The first poll only sets the
        starting point: what was typed before PrintWatch connected is not reported as new."""
        keys = [(entry.get("time"), entry.get("type"), entry.get("message")) for entry in entries]
        if self._console_cursor is None:
            self._console_cursor = keys[-1] if keys else ("empty",)
            return []
        new = entries
        for index in range(len(keys) - 1, -1, -1):
            if keys[index] == self._console_cursor:
                new = entries[index + 1 :]
                break
        if keys:
            self._console_cursor = keys[-1]
        return new

    async def _poll_console(self) -> None:
        try:
            sent = time.time()
            response = await self._http.get(f"{self._base_url}/server/gcode_store", params={"count": _CONSOLE_FETCH})
            received = time.time()
            response.raise_for_status()
            entries = response.json()["result"]["gcode_store"]
        except (httpx.HTTPError, ValueError, KeyError, TypeError):
            logger.debug("Console log not available from %s", self._base_url, exc_info=True)
            return
        self.clock.update(response.headers.get("date"), sent, received)

        now = time.monotonic()
        for entry in self._new_console_entries(entries):
            message = str(entry.get("message", ""))
            printer_time = entry.get("time")
            # The console log stamps entries with the printer's clock; corrected by the measured
            # offset, the command lands before the change it caused instead of at our poll time.
            detail = {"printer_time": _iso(printer_time), "clock_offset_s": _round(self.clock.seconds)}
            if entry.get("type") == "command":
                effects = [effect for effect, _ in line_effects(message, self._macros or {})]
                self._console.append(ConsoleCommand(message, printer_time, now, effects))
                await self._record(
                    "console_command",
                    EventOrigin.CONSOLE,
                    job_id=self._state.job_id,
                    after=message,
                    detail=detail,
                    ts=self.clock.to_local(printer_time),
                )
            elif message.startswith("!!"):
                await self._record(
                    "gcode_error",
                    EventOrigin.PRINTER,
                    job_id=self._state.job_id,
                    after=message,
                    detail=detail,
                    ts=self.clock.to_local(printer_time),
                )
        self._console = [command for command in self._console if now - command.seen_monotonic <= _CONSOLE_KEEP_SECONDS]

    async def _resolve(self, force: bool) -> None:
        now = math.inf if force else time.monotonic()
        still_pending = []
        for change in self._pending:
            decision = classify(change, self._console, self._file_index, self.file_scan_running and not force, now)
            if decision is None:
                still_pending.append(change)
                continue
            if decision.record:
                await self._record(
                    change.event_type,
                    decision.origin,
                    job_id=change.job_id,
                    field=change.field,
                    before=change.before,
                    after=change.after,
                    detail={**change.detail, "phase": change.phase, **decision.detail},
                    klipper_eventtime=change.klipper_eventtime,
                    ts=change.observed_at,
                )
        self._pending = still_pending

    async def _scan_file(self, filename: str) -> None:
        if self._macros is None:
            await self._load_macros()
        scanner = GcodeScanner(self._macros or {})
        complete = True
        started = time.monotonic()
        try:
            url = f"{self._base_url}/server/files/gcodes/{quote(filename)}"
            async with self._http.stream("GET", url) as response:
                response.raise_for_status()
                async for chunk in response.aiter_bytes(64 * 1024):
                    scanner.feed(chunk)
                    if scanner.bytes_scanned >= _SCAN_MAX_BYTES:
                        complete = False
                        break
                    ahead = scanner.bytes_scanned / _SCAN_BYTES_PER_SECOND - (time.monotonic() - started)
                    if ahead > 0:
                        await asyncio.sleep(ahead)
            if complete:
                scanner.finish()
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.warning("Could not index %s; its programmed changes will show as external", filename, exc_info=True)
            return
        self._file_index = FileIndex(filename, scanner.commands, scanner.bytes_scanned, complete)
        logger.info(
            "Indexed %s: %s bytes, %s relevant commands in %.1fs",
            filename,
            scanner.bytes_scanned,
            len(scanner.commands),
            time.monotonic() - started,
        )
