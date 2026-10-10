"""What a line of G-code changes, as far as the event log cares: heater targets, speed and flow
factors, fan speed, Z offset, excluded objects and the print state. Used for console commands
(read from Moonraker's gcode_store) and for the file being printed, following the macros a line
calls into their bodies (taken from the printer's configuration).

A heuristic, on purpose: macro bodies are Jinja templates, and only `{params.X}` values are
resolved; any other expression, and every branch of an `{% if %}`, counts as "may change this
field by an unknown amount" (Effect.value = None)."""

import bisect
import re
from dataclasses import dataclass

_MAX_MACRO_DEPTH = 3
_TEMPLATE_RE = re.compile(r"\{[^{}]*\}")
_PARAMS_RE = re.compile(r"^\s*params\.([A-Za-z_][A-Za-z0-9_]*)\s*(.*)$")
_DEFAULT_RE = re.compile(r"default\(\s*['\"]?([^'\")]*)['\"]?\s*\)")
_EXTENDED_PARAM_RE = re.compile(r"([A-Za-z_][A-Za-z0-9_]*)=(\"[^\"]*\"|'[^']*'|\S+)")
_CLASSIC_PARAM_RE = re.compile(r"\s([A-Za-z])(\S*)")
_UNRESOLVED = "?"


@dataclass(frozen=True)
class Effect:
    field: str  # Klipper object.field, e.g. "extruder.target", "gcode_move.homing_origin[2]"
    value: float | str | None  # None: changes the field by an amount that can't be known here


@dataclass(frozen=True)
class FileCommand:
    offset: int  # byte offset of the line in the file
    line: str
    effect: Effect
    via: str  # macro chain the effect comes from ("START_PRINT"), "" for a direct command


def _number(text: str | None) -> float | None:
    try:
        return float(text)
    except (TypeError, ValueError):
        return None


def _code(line: str) -> str:
    return line.split(";", 1)[0].strip()


def _extended_params(code: str) -> dict[str, str]:
    return {key.upper(): value.strip("\"'") for key, value in _EXTENDED_PARAM_RE.findall(code)}


def _classic_params(code: str) -> dict[str, str]:
    return {letter.upper(): value for letter, value in _CLASSIC_PARAM_RE.findall(" " + code.split(None, 1)[-1])}


def _heater_field(name: str) -> str:
    name = name.strip().lower()
    if name == "extruder" or re.fullmatch(r"extruder\d+", name):
        return f"{name}.target"
    if name == "heater_bed":
        return "heater_bed.target"
    return f"heater_generic {name}.target"


def direct_effects(line: str) -> list[Effect]:
    """Effects of a standard Klipper command, without looking into macros."""
    code = _code(line)
    if not code:
        return []
    command = code.split()[0].upper()
    classic = _classic_params(code) if re.fullmatch(r"[GMT]\d+", command) else {}
    extended = _extended_params(code)

    if command in ("M104", "M109"):
        tool = _number(classic.get("T"))
        field = f"extruder{int(tool)}.target" if tool else "extruder.target"
        return [Effect(field, _number(classic.get("S", "0")))]
    if command in ("M140", "M190"):
        return [Effect("heater_bed.target", _number(classic.get("S", "0")))]
    if command == "SET_HEATER_TEMPERATURE" and "HEATER" in extended:
        return [Effect(_heater_field(extended["HEATER"]), _number(extended.get("TARGET", "0")))]
    if command == "TURN_OFF_HEATERS":
        return [Effect("extruder.target", 0.0), Effect("heater_bed.target", 0.0)]
    if command == "M220" and "S" in classic:
        value = _number(classic["S"])
        return [Effect("gcode_move.speed_factor", None if value is None else value / 100)]
    if command == "M221" and "S" in classic:
        value = _number(classic["S"])
        return [Effect("gcode_move.extrude_factor", None if value is None else value / 100)]
    if command == "M106":
        value = _number(classic.get("S", "255"))
        return [Effect("fan.speed", None if value is None else min(value, 255.0) / 255)]
    if command == "M107":
        return [Effect("fan.speed", 0.0)]
    if command == "SET_FAN_SPEED" and "FAN" in extended:
        return [Effect(f"fan_generic {extended['FAN']}.speed", _number(extended.get("SPEED")))]
    if command == "SET_GCODE_OFFSET":
        if "Z_ADJUST" in extended:
            return [Effect("gcode_move.homing_origin[2]", None)]
        if "Z" in extended:
            return [Effect("gcode_move.homing_origin[2]", _number(extended["Z"]))]
        return []
    if command == "EXCLUDE_OBJECT" and "NAME" in extended:
        return [Effect("exclude_object.excluded_objects", extended["NAME"])]
    if command in ("PAUSE", "M600", "M601"):
        return [Effect("print_stats.state", "paused")]
    if command in ("RESUME", "M602"):
        return [Effect("print_stats.state", "printing")]
    if command == "CANCEL_PRINT":
        return [Effect("print_stats.state", "cancelled")]
    if command == "SDCARD_PRINT_FILE":
        return [Effect("print_stats.state", "printing")]
    return []


def _resolve_template(expression: str, params: dict[str, str]) -> str:
    match = _PARAMS_RE.match(expression)
    if match is None:
        return _UNRESOLVED
    name, filters = match.group(1).upper(), match.group(2)
    if name in params:
        return params[name]
    default = _DEFAULT_RE.search(filters)
    return default.group(1) if default else _UNRESOLVED


def _substitute(line: str, params: dict[str, str]) -> str:
    return _TEMPLATE_RE.sub(lambda match: _resolve_template(match.group(0)[1:-1], params), line)


def line_effects(line: str, macros: dict[str, str], depth: int = 0) -> list[tuple[Effect, str]]:
    """Effects of a line, following macro calls into their bodies. Each effect comes with the
    macro chain it was found through ("" when the line itself does it). macros maps the upper-case
    macro name to its gcode template."""
    code = _code(line)
    if not code:
        return []
    effects = [(effect, "") for effect in direct_effects(code)]
    name = code.split()[0].upper()
    body = macros.get(name)
    if body is None or depth >= _MAX_MACRO_DEPTH:
        return effects

    # Klipper passes "M600 X10" style parameters to macros named like G/M codes, KEY=VALUE otherwise.
    classic = _classic_params(code) if re.fullmatch(r"[GMT]\d+", name) else {}
    params = {**classic, **_extended_params(code)}
    for body_line in body.splitlines():
        stripped = body_line.strip()
        if not stripped or stripped.startswith(("{%", "#", ";")):
            continue
        for effect, via in line_effects(_substitute(stripped, params), macros, depth + 1):
            effects.append((effect, f"{name} > {via}" if via else name))
    return effects


def explains(effect: Effect, field: str, value) -> bool:
    """Whether an effect accounts for a field ending up at value."""
    if effect.field != field:
        return False
    if effect.value is None:
        return True
    if isinstance(effect.value, float) and isinstance(value, (int, float)) and not isinstance(value, bool):
        if field.endswith(".target"):
            tolerance = 0.5  # degrees
        elif field.endswith(".speed"):
            tolerance = 0.01  # fan: M106 S128 reports 0.50196
        else:
            tolerance = 1e-3
        return abs(effect.value - value) <= tolerance
    return effect.value == value


def macros_from_config(config: dict) -> dict[str, str]:
    """Macro templates from configfile.config, keyed by upper-case macro name."""
    return {
        name.split(" ", 1)[1].strip().upper(): str(section.get("gcode", ""))
        for name, section in config.items()
        if name.lower().startswith("gcode_macro ") and isinstance(section, dict)
    }


class GcodeScanner:
    """Indexes a G-code file fed in chunks: keeps only the lines that change a watched field,
    with their byte offsets, so a change seen while Klipper was at file position P can be traced
    to the line that caused it."""

    def __init__(self, macros: dict[str, str]) -> None:
        self._macros = macros
        self._offset = 0
        self._rest = b""
        self.commands: list[FileCommand] = []

    @property
    def bytes_scanned(self) -> int:
        return self._offset + len(self._rest)

    def feed(self, chunk: bytes) -> None:
        lines = (self._rest + chunk).split(b"\n")
        self._rest = lines.pop()
        for raw in lines:
            self._line(raw)
            self._offset += len(raw) + 1

    def finish(self) -> None:
        if self._rest:
            self._line(self._rest)
            self._offset += len(self._rest)
            self._rest = b""

    def _line(self, raw: bytes) -> None:
        stripped = raw.lstrip()
        # Moves and comments are nearly the whole file and never change a watched field.
        if not stripped or stripped[:1] in (b";", b"G", b"g"):
            return
        text = stripped.decode("utf-8", errors="replace").strip()
        for effect, via in line_effects(text, self._macros):
            self.commands.append(FileCommand(self._offset, text, effect, via))


class FileIndex:
    def __init__(self, filename: str, commands: list[FileCommand], bytes_scanned: int, complete: bool) -> None:
        self.filename = filename
        self.commands = sorted(commands, key=lambda command: command.offset)
        self._offsets = [command.offset for command in self.commands]
        self.bytes_scanned = bytes_scanned
        self.complete = complete

    def covers(self, position: int | None) -> bool:
        return position is not None and (self.complete or position <= self.bytes_scanned)

    def find(self, field: str, value, start: int, end: int) -> FileCommand | None:
        """The last command between byte offsets start and end that explains field = value."""
        low = bisect.bisect_left(self._offsets, start)
        high = bisect.bisect_right(self._offsets, end)
        for command in reversed(self.commands[low:high]):
            if explains(command.effect, field, value):
                return command
        return None
