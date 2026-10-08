"""Read-only discovery of what a Klipper/Moonraker printer exposes, saved to files for analysis.

Every request goes through ReadOnlyMoonraker, which only issues GET requests to an allowlist of
read endpoints, and the WebSocket session only accepts methods that read state. Nothing here can
send G-code, move the printer, change a temperature or start/stop a print.

The evidence that is lost soonest is saved first: the G-code console store lives in memory (gone
after a restart) and the logs rotate.

If the printer asks for credentials anywhere, the run stops there; it never tries to authenticate.

Usage, from the repo root and on the printer's network, with the printer idle:
    backend\\.venv\\Scripts\\python.exe backend\\scripts\\moonraker_discovery.py --url http://192.168.10.22:7125
WebSocket measurement only (downloads nothing, safe while printing):
    backend\\.venv\\Scripts\\python.exe backend\\scripts\\moonraker_discovery.py --only-ws --ws-seconds 600
"""

import argparse
import asyncio
import json
import re
import sys
import time
from collections import Counter
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.parse import quote, urlsplit, urlunsplit

import httpx
import websockets

try:
    from PIL import Image
except ImportError:  # only used to report snapshot resolutions
    Image = None

ROOT_DIR = Path(__file__).resolve().parents[2]
DEFAULT_OUT_DIR = ROOT_DIR / "docs" / "moonraker_discovery"

# Moonraker read endpoints. POST endpoints (print control, G-code scripts, restarts) are absent on
# purpose, and only GET is ever issued.
_ALLOWED_GET_PREFIXES = (
    "/printer/info",
    "/printer/objects/list",
    "/printer/objects/query",
    "/server/info",
    "/server/gcode_store",
    "/server/history/list",
    "/server/history/totals",
    "/server/files/list",
    "/server/files/metadata",
    "/server/files/logs/",
    "/server/files/gcodes/",
    "/server/files/klippy.log",
    "/server/files/moonraker.log",
    "/server/webcams/list",
    "/machine/system_info",
    "/machine/proc_stats",
)
# Webcam URLs come from the printer's own configuration; they may point anywhere on the printer
# host except back into the API.
_API_PATH_PREFIXES = ("/printer/", "/server/", "/machine/", "/access/", "/api/", "/websocket")
_ALLOWED_WS_METHODS = frozenset(
    {"server.info", "printer.info", "printer.objects.list", "printer.objects.query", "printer.objects.subscribe"}
)

# The 2026-09-25 resume incident (docs/moonraker_discovery/incidente_reanudacion.md).
_INCIDENT_FILE = "BOX FINAL lista pa imprimir_PETG_2h5m.gcode"
_INCIDENT_MARKER = "292.424 249.610 28.401"
_INCIDENT_WINDOW_START = 12380.0  # Klipper eventtime ~40 s before the pause started
_KLIPPY_LINES_BEFORE = 5000
_KLIPPY_LINES_AFTER = 300
_MOONRAKER_CONTEXT_LINES = 3
_MOONRAKER_MAX_LINES = 3000

_STATS_RE = re.compile(r"^Stats (\d+(?:\.\d+)?):")
_SD_EXIT_RE = re.compile(r"Exiting SD card print \(position (\d+)\)")
_MOONRAKER_PATTERN = re.compile(
    r"/printer/print/|printer\.print\.|Move out of range|key243|\bPAUSE\b|\bRESUME\b", re.IGNORECASE
)

_GCODE_HEAD_BYTES = 64 * 1024
_GCODE_TAIL_BYTES = 128 * 1024
_GCODE_ERROR_WINDOW_BEFORE = 8 * 1024
_GCODE_ERROR_WINDOW_AFTER = 1024
_MAX_FULL_READ = 300 * 1024 * 1024
_WS_SAMPLE_LIMIT = 2000
_FALLBACK_BED_MAX_MM = 260.0  # Creality Hi spec sheet, used only when configfile has no limits

_REDACTED_KEY_RE = re.compile(r"serial|mac_address", re.IGNORECASE)
_COLOMBIA = timezone(timedelta(hours=-5), "COT")  # no daylight saving time

# First word of the object/section names that ship with upstream Klipper. Anything else is
# reported as "not recognized" (likely Creality's own modules).
_KLIPPER_STANDARD_MODULES = frozenset(
    {
        "adc_temperature", "adxl345", "angle", "axis_twist_compensation", "bed_mesh", "bed_screws", "bltouch",
        "board_pins", "configfile", "controller_fan", "display", "display_status", "dotstar", "dual_carriage",
        "duplicate_pin_override", "endstop_phase",
        "exclude_object", "extruder", "extruder_stepper", "fan", "fan_generic", "filament_motion_sensor",
        "filament_switch_sensor", "firmware_retraction", "force_move", "gcode", "gcode_arcs", "gcode_button",
        "gcode_macro", "gcode_move", "hall_filament_width_sensor", "heater_bed", "heater_fan", "heater_generic",
        "heaters", "homing_override", "idle_timeout", "input_shaper", "led", "lis2dw", "manual_probe",
        "manual_stepper", "mcu", "menu", "motion_report", "mpu9250", "multi_pin", "neopixel", "output_pin",
        "palette2", "pause_resume", "pca9533", "pca9632", "pid_calibrate", "print_stats", "printer", "probe",
        "probe_eddy_current", "pwm_cycle_time", "pwm_tool", "quad_gantry_level", "query_adc", "query_endstops",
        "resonance_tester", "respond", "safe_z_home", "save_variables", "screws_tilt_adjust", "sdcard_loop",
        "servo", "skew_correction", "smart_effector", "static_digital_output", "system_stats",
        "temperature_combined", "temperature_fan", "temperature_host", "temperature_probe", "temperature_sensor",
        "thermistor", "tmc2130", "tmc2208", "tmc2209",
        "tmc2240", "tmc2660", "tmc5160", "toolhead", "tsl1401cl_filament_width_sensor", "verify_heater",
        "virtual_sdcard", "webhooks", "z_thermal_adjust", "z_tilt",
    }
)
_RELEVANT_MACROS = ("PAUSE", "RESUME", "CANCEL_PRINT", "END_PRINT", "PRINT_END", "START_PRINT", "PRINT_START", "M600")

_UNREACHABLE_HELP = """No se pudo hablar con Moonraker en {url}.
Antes de reintentar, revisa:
  1. VPN HotspotShield desconectada.
  2. Sesion `wsl -- sleep infinity` abierta.
  3. `curl.exe {url}/printer/info` respondiendo."""


class AuthenticationRequired(Exception):
    """The printer asked for credentials. The run stops instead of trying any."""

    def __init__(self, url: str) -> None:
        super().__init__(url)
        self.url = url


class ReadOnlyMoonraker:
    def __init__(self, base_url: str, timeout: float, throttle_kb_s: float | None = None) -> None:
        self.base_url = base_url.rstrip("/")
        self.host = urlsplit(self.base_url).hostname
        # Caps the download speed (a pause after each chunk) so reading a big file doesn't compete
        # with a print for the printer's small CPU and storage.
        self.throttle_kb_s = throttle_kb_s
        self.requests: list[dict] = []
        self.first_date_header: str | None = None
        self._client = httpx.AsyncClient(timeout=timeout, follow_redirects=False)

    async def close(self) -> None:
        await self._client.aclose()

    def _resolve(self, url_or_path: str) -> str:
        return url_or_path if "://" in url_or_path else self.base_url + url_or_path

    def _check_allowed(self, url: str, *, api: bool) -> None:
        parts = urlsplit(url)
        if parts.hostname != self.host:
            raise ValueError(f"Solo se consulta la impresora ({self.host}), no {parts.hostname}")
        if api and not parts.path.startswith(_ALLOWED_GET_PREFIXES):
            raise ValueError(f"Ruta fuera de la lista de solo lectura: {parts.path}")
        if not api and parts.path.startswith(_API_PATH_PREFIXES):
            raise ValueError(f"Una URL de camara no puede apuntar a la API de Moonraker: {parts.path}")

    async def get_json(self, path: str, params: dict | None = None):
        """Moonraker wraps every answer in {"result": ...}; returns None when the request failed."""
        url = self._resolve(path)
        self._check_allowed(url, api=True)
        entry = {"url": url, "params": params, "utc": _utc_now()}
        started = time.monotonic()
        try:
            response = await self._client.get(url, params=params)
        except httpx.HTTPError as error:
            entry["error"] = f"{type(error).__name__}: {error}"
            self.requests.append(entry)
            return None

        entry.update(status=response.status_code, bytes=len(response.content), ms=_ms_since(started))
        self.requests.append(entry)
        if self.first_date_header is None:
            self.first_date_header = response.headers.get("date")
        if response.status_code in (401, 403):
            raise AuthenticationRequired(url)
        if response.status_code != 200:
            return None
        try:
            return response.json().get("result")
        except (ValueError, AttributeError):
            return None

    async def stream_get(
        self,
        url_or_path: str,
        on_chunk,
        *,
        api: bool = True,
        headers: dict | None = None,
        max_bytes: int,
        max_seconds: float | None = None,
    ) -> dict:
        """GET that hands the body to on_chunk as it arrives and stops at max_bytes/max_seconds, so
        a huge log or an endless MJPEG stream can't hang the run."""
        url = self._resolve(url_or_path)
        self._check_allowed(url, api=api)
        entry: dict = {"url": url, "headers": headers, "utc": _utc_now()}
        started = time.monotonic()
        received = 0
        try:
            async with self._client.stream("GET", url, headers=headers) as response:
                entry.update(status=response.status_code, content_type=response.headers.get("content-type"))
                if response.status_code in (401, 403):
                    raise AuthenticationRequired(url)
                if response.status_code in (200, 206):
                    async for chunk in response.aiter_bytes():
                        on_chunk(chunk)
                        received += len(chunk)
                        if self.throttle_kb_s:
                            await asyncio.sleep(len(chunk) / (self.throttle_kb_s * 1024))
                        if received >= max_bytes or (
                            max_seconds is not None and time.monotonic() - started >= max_seconds
                        ):
                            entry["cortado"] = True
                            break
        except httpx.HTTPError as error:
            entry["error"] = f"{type(error).__name__}: {error}"
        finally:
            entry.update(bytes=received, ms=_ms_since(started))
            self.requests.append(entry)
        return entry

    async def download(self, path: str, dest: Path, max_bytes: int) -> dict:
        entry: dict = {}
        try:
            with dest.open("wb") as file:
                entry = await self.stream_get(path, file.write, max_bytes=max_bytes)
        finally:
            if entry.get("status") not in (200, 206):
                dest.unlink(missing_ok=True)
        return entry

    async def fetch_bytes(self, url_or_path: str, *, max_bytes: int, **kwargs) -> tuple[dict, bytes]:
        buffer = bytearray()
        entry = await self.stream_get(url_or_path, buffer.extend, max_bytes=max_bytes, **kwargs)
        return entry, bytes(buffer)

    async def fetch_tail(self, path: str, size: int) -> tuple[dict, bytes]:
        """Last `size` bytes of a file. Asks for a suffix range; if the server ignores it and
        sends the whole file, keeps only the end while streaming."""
        buffer = bytearray()

        def keep_last(chunk: bytes) -> None:
            buffer.extend(chunk)
            if len(buffer) > size:
                del buffer[: len(buffer) - size]

        entry = await self.stream_get(
            path, keep_last, headers={"Range": f"bytes=-{size}"}, max_bytes=_MAX_FULL_READ
        )
        return entry, bytes(buffer)

    async def fetch_window(self, path: str, start: int, end: int) -> tuple[dict, bytes]:
        """Bytes start..end (inclusive) of a file, with or without range support on the server."""
        entry, data = await self.fetch_bytes(path, max_bytes=end + 1, headers={"Range": f"bytes={start}-{end}"})
        if entry.get("status") == 200:
            data = data[start : end + 1]
        return entry, data


class _ReadOnlyRpc:
    """JSON-RPC over Moonraker's WebSocket, limited to methods that read state. Notifications that
    arrive while waiting for an answer are kept so the measurement doesn't lose them."""

    def __init__(self, ws) -> None:
        self._ws = ws
        self._next_id = 1
        self.early_messages: list[tuple[float, str]] = []

    async def call(self, method: str, params: dict | None = None, timeout: float = 20.0):
        if method not in _ALLOWED_WS_METHODS:
            raise ValueError(f"Metodo no permitido (solo lectura): {method}")
        request_id = self._next_id
        self._next_id += 1
        await self._ws.send(json.dumps({"jsonrpc": "2.0", "method": method, "params": params or {}, "id": request_id}))

        deadline = time.monotonic() + timeout
        while True:
            raw = await asyncio.wait_for(self._ws.recv(), timeout=max(0.1, deadline - time.monotonic()))
            try:
                message = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if message.get("id") != request_id:
                self.early_messages.append((time.time(), raw))
                continue
            error = message.get("error")
            if error:
                if error.get("code") in (401, 403):
                    raise AuthenticationRequired(f"websocket:{method}")
                raise RuntimeError(f"{method}: {error}")
            return message.get("result")


class _WsStats:
    def __init__(self, sample_path: Path) -> None:
        self.started = time.monotonic()
        self.messages = 0
        self.bytes = 0
        self.methods: Counter = Counter()
        self.fields: dict[str, dict] = {}
        self.status_eventtimes: list[float] = []
        self.gcode_responses: list[str] = []
        self._sample = sample_path.open("w", encoding="utf-8")
        self._sample_left = _WS_SAMPLE_LIMIT

    def close(self) -> None:
        self._sample.close()

    def add(self, received_at: float, raw: str) -> None:
        self.messages += 1
        self.bytes += len(raw.encode("utf-8"))
        try:
            message = json.loads(raw)
        except json.JSONDecodeError:
            self.methods["(no JSON)"] += 1
            return

        if self._sample_left > 0:
            self._sample.write(json.dumps({"recibido_utc": _fmt_unix(received_at), "mensaje": message}) + "\n")
            self._sample_left -= 1

        method = message.get("method", "(respuesta)")
        self.methods[method] += 1
        params = message.get("params") or []
        if method == "notify_status_update" and params and isinstance(params[0], dict):
            if len(params) > 1 and isinstance(params[1], (int, float)):
                self.status_eventtimes.append(float(params[1]))
            for name, value in _flatten(params[0]):
                self._add_field(name, value)
        elif method == "notify_gcode_response":
            self.gcode_responses.extend(f"{_fmt_unix(received_at)}  {line}" for line in params)

    def _add_field(self, name: str, value) -> None:
        entry = self.fields.setdefault(name, {"actualizaciones": 0, "min": None, "max": None, "ultimo": None})
        entry["actualizaciones"] += 1
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            entry["min"] = value if entry["min"] is None else min(entry["min"], value)
            entry["max"] = value if entry["max"] is None else max(entry["max"], value)
        entry["ultimo"] = _short(value)

    def result(self, printer_state: str) -> dict:
        seconds = max(time.monotonic() - self.started, 1e-6)
        intervals = sorted(b - a for a, b in zip(self.status_eventtimes, self.status_eventtimes[1:]))
        median_interval = intervals[len(intervals) // 2] if intervals else None
        return {
            "estado_impresora": printer_state,
            "segundos": round(seconds, 1),
            "mensajes": self.messages,
            "bytes": self.bytes,
            "bytes_por_segundo": round(self.bytes / seconds, 1),
            "extrapolacion_2h_mb": round(self.bytes / seconds * 7200 / 1e6, 1),
            "por_metodo": dict(self.methods.most_common()),
            "intervalo_mediano_entre_actualizaciones_s": None if median_interval is None else round(median_interval, 3),
            "campos": {
                name: {**entry, "hz": round(entry["actualizaciones"] / seconds, 3)}
                for name, entry in sorted(self.fields.items())
            },
        }


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _fmt_unix(timestamp) -> str:
    if not isinstance(timestamp, (int, float)):
        return ""
    return datetime.fromtimestamp(timestamp, timezone.utc).isoformat(timespec="seconds")


def _ms_since(started: float) -> int:
    return round((time.monotonic() - started) * 1000)


def _safe_name(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", name).strip("_") or "archivo"


def _write_json(path: Path, data) -> None:
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False, default=str), encoding="utf-8")


def _read_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _redact(data):
    """Serial numbers and MAC addresses identify the device and add nothing to the analysis."""
    if isinstance(data, dict):
        return {key: "<oculto>" if _REDACTED_KEY_RE.search(key) else _redact(value) for key, value in data.items()}
    if isinstance(data, list):
        return [_redact(item) for item in data]
    return data


def _short(value, limit: int = 60) -> str:
    if isinstance(value, float):
        text = f"{value:.4g}"
    elif isinstance(value, list) and all(isinstance(item, (int, float)) for item in value):
        text = "[" + ", ".join(f"{item:.4g}" if isinstance(item, float) else str(item) for item in value) + "]"
    else:
        text = json.dumps(value, ensure_ascii=False, default=str)
    return text if len(text) <= limit else text[: limit - 3] + "..."


def _flatten(status: dict, prefix: str = "", depth: int = 0):
    """object.field pairs, opening nested dicts (print_stats.info) and short numeric lists
    (toolhead.position) so each scalar gets its own update count and range."""
    for key, value in status.items():
        name = f"{prefix}{key}"
        if isinstance(value, dict) and depth < 2:
            yield from _flatten(value, f"{name}.", depth + 1)
        elif (
            isinstance(value, list)
            and 0 < len(value) <= 4
            and all(isinstance(item, (int, float)) and not isinstance(item, bool) for item in value)
        ):
            for index, item in enumerate(value):
                yield f"{name}[{index}]", item
        else:
            yield name, value


def _to_float(value) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _websocket_url(base_url: str) -> str:
    parts = urlsplit(base_url)
    scheme = "wss" if parts.scheme == "https" else "ws"
    return urlunsplit((scheme, parts.netloc, "/websocket", "", ""))


def _is_standard_module(name: str) -> bool:
    module = name.split(" ", 1)[0]
    return module in _KLIPPER_STANDARD_MODULES or module.startswith("stepper_")


# --- Steps -------------------------------------------------------------------------------------


async def _run_step(report: dict, name: str, coro) -> None:
    try:
        report["pasos"][name] = await coro
    except AuthenticationRequired:
        raise
    except Exception as error:  # one broken step must not lose what the others collect
        report["pasos"][name] = {"ok": False, "detalle": f"{type(error).__name__}: {error}"}
    print(f"  {name}: {'ok' if report['pasos'][name].get('ok') else 'fallo o incompleto'}")


async def _save_gcode_store(moon: ReadOnlyMoonraker, out: Path) -> dict:
    result = await moon.get_json("/server/gcode_store", {"count": 10000})
    if result is None:
        return {"ok": False, "detalle": "sin respuesta de /server/gcode_store"}
    entries = result.get("gcode_store", [])
    _write_json(out / "gcode_store.json", entries)
    text = "\n".join(
        f"{_fmt_unix(entry.get('time'))}  {entry.get('type', '?'):<8}  {entry.get('message', '')}" for entry in entries
    )
    (out / "gcode_store.txt").write_text(text + "\n", encoding="utf-8")
    return {
        "ok": True,
        "lineas": len(entries),
        "desde_utc": _fmt_unix(entries[0].get("time")) if entries else None,
        "archivos": ["gcode_store.json", "gcode_store.txt"],
    }


async def _save_logs(moon: ReadOnlyMoonraker, out: Path, ctx: dict) -> dict:
    args = ctx["args"]
    logs_dir = out / "logs"
    logs_dir.mkdir(exist_ok=True)
    max_bytes = int(args.max_log_mb * 1024 * 1024)

    listing = await moon.get_json("/server/files/list", {"root": "logs"})
    downloads = []
    if isinstance(listing, list):
        _write_json(logs_dir / "logs_list.json", listing)
        for item in listing:
            path = item.get("path", "")
            if not args.all_logs and not Path(path).name.startswith(("klippy", "moonraker")):
                continue
            entry = await moon.download("/server/files/logs/" + quote(path), logs_dir / _safe_name(path), max_bytes)
            downloads.append(
                {
                    "archivo": path,
                    "tamano": item.get("size"),
                    "modificado_utc": _fmt_unix(item.get("modified")),
                    "descargado": entry.get("bytes"),
                    "cortado": entry.get("cortado", False),
                }
            )
    else:
        # Moonraker without a "logs" root only serves the current files.
        for name in ("klippy.log", "moonraker.log"):
            entry = await moon.download(f"/server/files/{name}", logs_dir / name, max_bytes)
            downloads.append({"archivo": name, "descargado": entry.get("bytes"), "cortado": entry.get("cortado", False)})

    excerpts = _write_incident_excerpts(logs_dir, ctx)
    return {
        "ok": any(item.get("descargado") for item in downloads),
        "logs": downloads,
        **excerpts,
    }


def _klippy_incident_excerpt(lines: list[str]) -> tuple[list[str], int | None]:
    """Lines around the incident's error in one klippy log, starting ~40 s before the pause, and
    the G-code file position where the print stopped if Klipper logged it."""
    hits = [index for index, line in enumerate(lines) if _INCIDENT_MARKER in line]
    if not hits:
        return [], None

    first = hits[0]
    last = max(index for index in hits if index - first < 2000)
    start = first
    while start > 0 and first - start < _KLIPPY_LINES_BEFORE:
        match = _STATS_RE.match(lines[start - 1])
        if match and float(match.group(1)) < _INCIDENT_WINDOW_START:
            break
        start -= 1

    excerpt = lines[start : min(len(lines), last + _KLIPPY_LINES_AFTER)]
    position = None
    for line in excerpt:
        match = _SD_EXIT_RE.search(line)
        if match:
            position = int(match.group(1))
    return excerpt, position


def _moonraker_incident_excerpt(lines: list[str]) -> list[str]:
    """Print-control requests and errors with a few lines of context; '...' marks skipped lines."""
    keep: set[int] = set()
    for index, line in enumerate(lines):
        if _MOONRAKER_PATTERN.search(line):
            keep.update(range(max(0, index - _MOONRAKER_CONTEXT_LINES), min(len(lines), index + _MOONRAKER_CONTEXT_LINES + 1)))

    excerpt: list[str] = []
    previous = None
    for index in sorted(keep)[:_MOONRAKER_MAX_LINES]:
        if previous is not None and index != previous + 1:
            excerpt.append("...")
        excerpt.append(lines[index])
        previous = index
    return excerpt


def _write_incident_excerpts(logs_dir: Path, ctx: dict) -> dict:
    klippy_parts: list[str] = []
    moonraker_parts: list[str] = []
    for path in sorted(logs_dir.iterdir()):
        if not path.is_file() or path.suffix == ".json" or path.name.startswith("extracto_"):
            continue
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        if path.name.startswith("klippy"):
            excerpt, position = _klippy_incident_excerpt(lines)
            if excerpt:
                klippy_parts += [f"===== {path.name} =====", *excerpt, ""]
                if position is not None:
                    ctx["error_file_position"] = position
        elif path.name.startswith("moonraker"):
            excerpt = _moonraker_incident_excerpt(lines)
            if excerpt:
                moonraker_parts += [f"===== {path.name} =====", *excerpt, ""]

    generated = f"Generado por backend/scripts/moonraker_discovery.py el {_utc_now()} (UTC)."
    files = []
    if klippy_parts:
        header = [
            f'# Extracto de klippy.log alrededor del error "Move out of range: {_INCIDENT_MARKER}".',
            f"# Desde ~40 s antes de la pausa (eventtime {_INCIDENT_WINDOW_START:.0f}) hasta {_KLIPPY_LINES_AFTER} lineas despues del error.",
            f"# {generated}",
            "",
        ]
        (logs_dir / "extracto_klippy_incidente.txt").write_text("\n".join(header + klippy_parts) + "\n", encoding="utf-8")
        files.append("logs/extracto_klippy_incidente.txt")
    if moonraker_parts:
        header = [
            "# Extracto de moonraker.log: peticiones de control de impresion (pause/resume/cancel) y errores,",
            f"# con {_MOONRAKER_CONTEXT_LINES} lineas de contexto. Las horas del log estan en la zona horaria de la impresora.",
            f"# {generated}",
            "",
        ]
        (logs_dir / "extracto_moonraker_incidente.txt").write_text(
            "\n".join(header + moonraker_parts) + "\n", encoding="utf-8"
        )
        files.append("logs/extracto_moonraker_incidente.txt")

    return {
        "incidente_en_klippy_log": bool(klippy_parts),
        "posicion_del_error_en_el_gcode": ctx.get("error_file_position"),
        "extractos": files,
    }


async def _save_history(moon: ReadOnlyMoonraker, out: Path, ctx: dict) -> dict:
    history = await moon.get_json("/server/history/list", {"limit": 100, "order": "desc"})
    if history is None:
        return {"ok": False, "detalle": "sin respuesta de /server/history/list"}
    _write_json(out / "history_list.json", history)
    totals = await moon.get_json("/server/history/totals")
    if totals is not None:
        _write_json(out / "history_totals.json", totals)

    jobs = history.get("jobs", [])
    rows = [
        f"{_fmt_unix(job.get('start_time')):<26} {_fmt_unix(job.get('end_time')):<26} {job.get('status', '?'):<16} "
        f"{(job.get('total_duration') or 0) / 60:7.1f} min  {job.get('filename', '')}"
        for job in jobs
    ]
    header = f"{'inicio (UTC)':<26} {'fin (UTC)':<26} {'estado':<16} {'duracion':>11}  archivo"
    (out / "historial.txt").write_text("\n".join([header, *rows]) + "\n", encoding="utf-8")

    ctx["history_files"] = [job["filename"] for job in jobs if job.get("filename")]
    return {
        "ok": True,
        "trabajos": len(jobs),
        "con_el_archivo_del_incidente": sum(1 for job in jobs if job.get("filename") == _INCIDENT_FILE),
        "archivos": ["history_list.json", "history_totals.json", "historial.txt"],
    }


async def _save_objects(moon: ReadOnlyMoonraker, out: Path, ctx: dict) -> dict:
    listing = await moon.get_json("/printer/objects/list")
    if not listing:
        return {"ok": False, "detalle": "sin respuesta de /printer/objects/list"}
    objects = listing.get("objects", [])
    _write_json(out / "objects.json", listing)
    ctx["objects"] = objects

    result = await moon.get_json("/printer/objects/query?" + "&".join(quote(name) for name in objects))
    if not result:
        return {"ok": False, "objetos": len(objects), "detalle": "fallo la consulta del estado de los objetos"}
    status = dict(result.get("status", {}))
    configfile = status.pop("configfile", None)
    _write_json(out / "objects_status.json", {"eventtime": result.get("eventtime"), "status": status})
    ctx["status"] = status
    files = ["objects.json", "objects_status.json"]
    if configfile is not None:
        _write_json(out / "configfile.json", configfile)
        ctx["settings"] = configfile.get("settings") or {}
        ctx["config"] = configfile.get("config") or {}
        files.append("configfile.json")
    return {
        "ok": True,
        "objetos": len(objects),
        "no_reconocidos": [name for name in objects if not _is_standard_module(name)],
        "archivos": files,
    }


def _format_config_section(name: str, section: dict) -> str:
    lines = [f"[{name}]"]
    for key, value in section.items():
        text = str(value)
        if "\n" in text:
            lines.append(f"{key}:")
            lines.extend(f"  {line}" for line in text.strip("\n").splitlines())
        else:
            lines.append(f"{key}: {text}")
    return "\n".join(lines)


async def _analyze_config(out: Path, ctx: dict) -> dict:
    settings = ctx.get("settings") or {}
    config = ctx.get("config") or {}
    if not settings and not config:
        return {"ok": False, "detalle": "no hay objeto configfile"}

    for axis in "xyz":
        ctx.setdefault("axis_max", {})[axis] = _to_float(settings.get(f"stepper_{axis}", {}).get("position_max"))

    printer = settings.get("printer", {})
    lines = [
        "# Configuración de Klipper (análisis automático)",
        "",
        "Fuente: objeto `configfile` (`configfile.json`). Lo regenera `moonraker_discovery.py` en cada corrida.",
        "",
        "## Límites de los ejes",
        "",
        "| Eje | position_min | position_max | position_endstop |",
        "|---|---|---|---|",
    ]
    for axis in ("stepper_x", "stepper_y", "stepper_z"):
        section = settings.get(axis, {})
        lines.append(
            f"| {axis} | {section.get('position_min', '-')} | {section.get('position_max', '-')} "
            f"| {section.get('position_endstop', '-')} |"
        )
    lines += [
        "",
        f"Cinemática `{printer.get('kinematics', '-')}`, max_velocity {printer.get('max_velocity', '-')} mm/s, "
        f"max_accel {printer.get('max_accel', '-')} mm/s².",
        "",
    ]

    mesh = settings.get("bed_mesh")
    if mesh:
        lines += [
            "## Malla de la cama",
            "",
            f"mesh_min {mesh.get('mesh_min', '-')}, mesh_max {mesh.get('mesh_max', '-')}, "
            f"probe_count {mesh.get('probe_count', '-')}.",
            "",
        ]
    lines += [f"`exclude_object` configurado: {'sí' if 'exclude_object' in settings else 'no'}.", ""]

    macros = {name: section for name, section in config.items() if name.lower().startswith("gcode_macro ")}
    (out / "macros.cfg").write_text(
        "\n\n".join(_format_config_section(name, macros[name]) for name in sorted(macros)) + "\n", encoding="utf-8"
    )
    relevant = [
        name
        for name in sorted(macros)
        if name.split(" ", 1)[1].upper() in _RELEVANT_MACROS
        or any(word in name.upper() for word in ("PAUSE", "RESUME", "PARK"))
    ]
    lines += ["## Macros relevantes para el incidente", ""]
    for name in relevant:
        lines += [f"### `{name}`", "", "```", _format_config_section(name, macros[name]), "```", ""]
    if not relevant:
        lines += ["No se encontraron macros de pausa, reanudación o fin de impresión.", ""]
    lines += [f"Todas las macros ({len(macros)}) están en `macros.cfg`.", ""]

    unknown_sections = sorted(name for name in config if not _is_standard_module(name) and name != "printer")
    lines += ["## Secciones no reconocidas como Klipper estándar", ""]
    lines += [f"- `{name}`" for name in unknown_sections] or ["Ninguna."]
    (out / "analisis_config.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {"ok": True, "macros": len(macros), "macros_relevantes": relevant, "archivos": ["analisis_config.md", "macros.cfg"]}


_MOVE_RE = re.compile(r"^G[01]\b", re.IGNORECASE)
_AXIS_RE = re.compile(r"\b([XY])\s*(-?\d+(?:\.\d+)?)", re.IGNORECASE)
_STANDARD_CODE_RE = re.compile(r"^[GMT]\d+", re.IGNORECASE)
_COMMAND_RE = re.compile(r"^[A-Z_][A-Z0-9_]*")


def _executable_lines(text: str) -> list[str]:
    lines = []
    for line in text.splitlines():
        code = line.split(";", 1)[0].strip()
        if code:
            lines.append(code)
    return lines


def _out_of_range_moves(lines: list[str], axis_max: dict) -> list[str]:
    """Absolute G0/G1 moves whose literal X/Y exceed the axis limits. A heuristic: it ignores G92
    and offsets, and assumes absolute mode until it sees G91."""
    absolute = True
    found = []
    for line in lines:
        upper = line.upper()
        if upper.startswith("G90"):
            absolute = True
        elif upper.startswith("G91"):
            absolute = False
        elif absolute and _MOVE_RE.match(upper):
            for axis, value in _AXIS_RE.findall(upper):
                limit = axis_max.get(axis.lower())
                if limit is not None and float(value) > limit:
                    found.append(line)
                    break
    return found


def _non_standard_commands(lines: list[str]) -> list[str]:
    commands = []
    for line in lines:
        match = _COMMAND_RE.match(line.upper())
        if match and not _STANDARD_CODE_RE.match(line):
            commands.append(line)
    return commands


async def _inspect_gcode_file(moon: ReadOnlyMoonraker, gcode_dir: Path, name: str, ctx: dict) -> dict:
    metadata = await moon.get_json("/server/files/metadata", {"filename": name})
    if metadata is None:
        return {"archivo": name, "existe": False}
    safe = _safe_name(name)
    _write_json(gcode_dir / f"{safe}.metadata.json", metadata)
    path = "/server/files/gcodes/" + quote(name)

    _, head = await moon.fetch_bytes(path, max_bytes=_GCODE_HEAD_BYTES, headers={"Range": f"bytes=0-{_GCODE_HEAD_BYTES - 1}"})
    _, tail = await moon.fetch_tail(path, _GCODE_TAIL_BYTES)
    (gcode_dir / f"{safe}.inicio.gcode").write_bytes(head)
    (gcode_dir / f"{safe}.final.gcode").write_bytes(tail)

    tail_text = tail.decode("utf-8", errors="replace")
    if len(tail) == _GCODE_TAIL_BYTES:
        tail_text = tail_text.split("\n", 1)[-1]  # the range cut the first line in half
    head_lines = _executable_lines(head.decode("utf-8", errors="replace"))
    tail_lines = _executable_lines(tail_text)
    axis_max = {axis: ctx.get("axis_max", {}).get(axis) or _FALLBACK_BED_MAX_MM for axis in "xy"}

    result = {
        "archivo": name,
        "existe": True,
        "tamano": metadata.get("size"),
        "laminador": f"{metadata.get('slicer', '-')} {metadata.get('slicer_version', '')}".strip(),
        "altura_de_capa": metadata.get("layer_height"),
        "altura_del_objeto": metadata.get("object_height"),
        "fuera_de_rango": _out_of_range_moves(head_lines + tail_lines, axis_max),
        "comandos_no_estandar_al_final": _non_standard_commands(tail_lines[-200:]),
        "ultimas_lineas": tail_lines[-80:],
        "limites_usados": axis_max,
    }

    position = ctx.get("error_file_position")
    if name == _INCIDENT_FILE and position is not None:
        start = max(0, position - _GCODE_ERROR_WINDOW_BEFORE)
        _, window = await moon.fetch_window(path, start, position + _GCODE_ERROR_WINDOW_AFTER)
        (gcode_dir / f"{safe}.alrededor_del_error.gcode").write_bytes(window)
        result["ventana_del_error"] = f"bytes {start}-{position + _GCODE_ERROR_WINDOW_AFTER} (error en {position})"
    return result


def _write_gcode_analysis(path: Path, analyses: list[dict]) -> None:
    lines = [
        "# Archivos G-code (análisis automático)",
        "",
        "Fuente: `/server/files/metadata` y el inicio y el final de cada archivo (carpeta `gcode/`). La búsqueda",
        "de movimientos fuera de rango es heurística: mira valores literales de X/Y en modo absoluto e ignora G92",
        "y los desplazamientos de las macros.",
        "",
    ]
    for analysis in analyses:
        lines += [f"## `{analysis['archivo']}`", ""]
        if not analysis.get("existe"):
            lines += ["El archivo no está en la impresora (o Moonraker no devolvió sus metadatos).", ""]
            continue
        lines += [
            f"- Tamaño: {analysis.get('tamano')} bytes. Laminador: {analysis.get('laminador')}.",
            f"- Altura de capa: {analysis.get('altura_de_capa')} mm; altura del objeto: {analysis.get('altura_del_objeto')} mm.",
            f"- Límites usados: X ≤ {analysis['limites_usados']['x']}, Y ≤ {analysis['limites_usados']['y']} mm.",
            f"- Movimientos fuera de rango en el inicio y el final: {len(analysis['fuera_de_rango'])}.",
        ]
        if analysis.get("ventana_del_error"):
            lines.append(f"- Ventana alrededor de la posición del error: {analysis['ventana_del_error']}.")
        lines.append("")
        if analysis["fuera_de_rango"]:
            lines += ["```gcode", *analysis["fuera_de_rango"][:50], "```", ""]
        if analysis["comandos_no_estandar_al_final"]:
            lines += ["Comandos no estándar (macros o comandos extendidos) en las últimas 200 líneas:", "", "```gcode"]
            lines += [*dict.fromkeys(analysis["comandos_no_estandar_al_final"]), "```", ""]
        lines += ["Últimas 80 líneas ejecutables:", "", "```gcode", *analysis["ultimas_lineas"], "```", ""]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


async def _save_gcode_files(moon: ReadOnlyMoonraker, out: Path, ctx: dict) -> dict:
    gcode_dir = out / "gcode"
    gcode_dir.mkdir(exist_ok=True)
    listing = await moon.get_json("/server/files/list", {"root": "gcodes"})
    if listing is not None:
        _write_json(gcode_dir / "gcode_files.json", listing)

    current = (ctx.get("status") or {}).get("print_stats", {}).get("filename")
    names = list(dict.fromkeys(n for n in [*ctx["args"].gcode_file, _INCIDENT_FILE, current, *ctx.get("history_files", [])[:3]] if n))
    analyses = [await _inspect_gcode_file(moon, gcode_dir, name, ctx) for name in names]
    _write_gcode_analysis(out / "analisis_gcode.md", analyses)
    return {
        "ok": any(analysis.get("existe") for analysis in analyses),
        "revisados": {analysis["archivo"]: analysis.get("existe", False) for analysis in analyses},
        "archivos": ["analisis_gcode.md", "gcode/"],
    }


def _webcam_candidates(moon: ReadOnlyMoonraker, url: str | None) -> tuple[list[str], str | None]:
    if not url:
        return [], "sin URL"
    parts = urlsplit(url)
    if parts.scheme and parts.scheme not in ("http", "https"):
        return [], f"protocolo {parts.scheme}: no se prueba desde este script"
    if parts.scheme:
        if parts.hostname != moon.host:
            return [], f"apunta a otro equipo ({parts.hostname}): no se prueba"
        return [url], None
    path = url if url.startswith("/") else "/" + url
    # A relative URL is resolved by the web interface that shows it (nginx on port 80, Fluidd on
    # 4408 on Creality printers), so try those before Moonraker's own port.
    origins = [f"http://{moon.host}", f"http://{moon.host}:4408", moon.base_url]
    return [origin + path for origin in dict.fromkeys(origins)], None


def _jpeg_size(data: bytes) -> list[int] | None:
    if Image is None:
        return None
    try:
        from io import BytesIO

        with Image.open(BytesIO(data)) as image:
            return list(image.size)
    except Exception:
        return None


async def _probe_webcam(moon: ReadOnlyMoonraker, webcam_dir: Path, cam: dict, skip_stream: bool = False) -> dict:
    name = _safe_name(cam.get("name") or "webcam")
    result = {
        "nombre": cam.get("name"),
        "servicio": cam.get("service"),
        "fps_objetivo": cam.get("target_fps"),
        "snapshot_url": cam.get("snapshot_url"),
        "stream_url": cam.get("stream_url"),
    }

    candidates, note = _webcam_candidates(moon, cam.get("snapshot_url"))
    result["snapshot"] = {"nota": note} if note else {"ok": False}
    for url in candidates:
        entry, data = await moon.fetch_bytes(url, api=False, max_bytes=10 * 1024 * 1024, max_seconds=10)
        if entry.get("status") == 200 and data.startswith(b"\xff\xd8"):
            (webcam_dir / f"{name}_snapshot.jpg").write_bytes(data)
            result["snapshot"] = {"ok": True, "url": url, "bytes": len(data), "resolucion": _jpeg_size(data)}
            break

    candidates, note = _webcam_candidates(moon, cam.get("stream_url"))
    result["stream"] = {"nota": note} if note else {"ok": False}
    if skip_stream:
        # Reading an MJPEG stream for seconds loads the printer's camera pipeline; not during a print.
        result["stream"] = {"nota": "no se probó (--skip-webcam-stream)", "url_candidata": candidates[:1]}
        candidates = []
    for url in candidates:
        started = time.monotonic()
        entry, data = await moon.fetch_bytes(url, api=False, max_bytes=8 * 1024 * 1024, max_seconds=5)
        if entry.get("status") != 200 or b"\xff\xd8\xff" not in data:
            continue
        seconds = time.monotonic() - started
        frames = data.count(b"\xff\xd8\xff")
        first = data.index(b"\xff\xd8\xff")
        end = data.find(b"\xff\xd9", first)
        frame = data[first : end + 2] if end != -1 else b""
        if frame:
            (webcam_dir / f"{name}_stream_frame.jpg").write_bytes(frame)
        result["stream"] = {
            "ok": True,
            "url": url,
            "content_type": entry.get("content_type"),
            "cuadros": frames,
            "segundos": round(seconds, 1),
            "fps_aprox": round(frames / seconds, 1) if seconds > 0 else None,
            "resolucion": _jpeg_size(frame) if frame else None,
        }
        break
    return result


async def _save_webcams(moon: ReadOnlyMoonraker, out: Path, skip_stream: bool = False) -> dict:
    result = await moon.get_json("/server/webcams/list")
    if result is None:
        return {"ok": False, "detalle": "sin respuesta de /server/webcams/list"}
    _write_json(out / "webcams.json", result)
    webcam_dir = out / "webcam"
    webcam_dir.mkdir(exist_ok=True)
    probes = [await _probe_webcam(moon, webcam_dir, cam, skip_stream) for cam in result.get("webcams", [])]
    _write_json(out / "webcam_probe.json", probes)
    return {
        "ok": True,
        "camaras": len(probes),
        "con_imagen": [probe["nombre"] for probe in probes if probe["snapshot"].get("ok") or probe["stream"].get("ok")],
        "archivos": ["webcams.json", "webcam_probe.json", "webcam/"],
    }


async def _save_machine(moon: ReadOnlyMoonraker, out: Path) -> dict:
    system_info = await moon.get_json("/machine/system_info")
    proc_stats = await moon.get_json("/machine/proc_stats")
    files = []
    if system_info is not None:
        _write_json(out / "system_info.json", _redact(system_info))
        files.append("system_info.json")
    if proc_stats is not None:
        _write_json(out / "proc_stats.json", proc_stats)
        files.append("proc_stats.json")
    return {"ok": bool(files), "archivos": files}


def _handshake_status(error: Exception) -> int | None:
    # websockets reports the HTTP status differently in its legacy and new implementations.
    response = getattr(error, "response", None)
    if response is not None:
        return getattr(response, "status_code", None)
    return getattr(error, "status_code", None)


async def _measure_websocket(moon: ReadOnlyMoonraker, out: Path, ctx: dict, seconds: float) -> dict:
    ws_url = _websocket_url(moon.base_url)
    try:
        async with websockets.connect(ws_url, max_size=None, open_timeout=15) as ws:
            return await _measure_on(ws, out, ctx, seconds)
    except websockets.exceptions.InvalidHandshake as error:
        if _handshake_status(error) in (401, 403):
            raise AuthenticationRequired(ws_url) from error
        raise


async def _measure_on(ws, out: Path, ctx: dict, seconds: float) -> dict:
    rpc = _ReadOnlyRpc(ws)
    objects = ctx.get("objects")
    if not objects:
        objects = (await rpc.call("printer.objects.list")).get("objects", [])
        ctx["objects"] = objects
    # configfile never changes while running and is huge; everything else is measured.
    skip_macros = ctx["args"].ws_skip_macros
    # --ws-skip-macros: the ~70 gcode_macro objects hold static variables; every subscriber makes
    # Klipper query them each 250 ms, which is load a running print doesn't need.
    subscription = {
        name: None for name in objects if name != "configfile" and not (skip_macros and name.startswith("gcode_macro "))
    }
    initial = await rpc.call("printer.objects.subscribe", {"objects": subscription}) or {}
    initial_status = initial.get("status", {})
    printer_state = _safe_name(initial_status.get("print_stats", {}).get("state") or "desconocido")
    _write_json(out / f"ws_estado_inicial_{printer_state}.json", initial)
    print(f"  midiendo el WebSocket {seconds:.0f} s (estado de la impresora: {printer_state})...")

    sample_path = out / f"ws_muestra_{printer_state}.jsonl"
    stats = _WsStats(sample_path)
    try:
        for received_at, raw in rpc.early_messages:
            stats.add(received_at, raw)
        deadline = time.monotonic() + seconds
        while (remaining := deadline - time.monotonic()) > 0:
            try:
                raw = await asyncio.wait_for(ws.recv(), timeout=remaining)
            except asyncio.TimeoutError:
                break
            stats.add(time.time(), raw)
    finally:
        stats.close()

    measurement = stats.result(printer_state)
    measurement["medido_utc"] = _utc_now()
    measurement["objetos_suscritos"] = len(subscription)
    _write_json(out / f"ws_medicion_{printer_state}.json", measurement)
    if stats.gcode_responses:
        (out / f"ws_respuestas_gcode_{printer_state}.txt").write_text(
            "\n".join(stats.gcode_responses) + "\n", encoding="utf-8"
        )
    return {
        "ok": True,
        "estado_impresora": printer_state,
        "mensajes": measurement["mensajes"],
        "bytes_por_segundo": measurement["bytes_por_segundo"],
        "archivos": [f"ws_medicion_{printer_state}.json", f"ws_estado_inicial_{printer_state}.json", sample_path.name],
    }


# --- Summary ------------------------------------------------------------------------------------


def _clock_offset(date_header: str | None, local_utc: datetime) -> float | None:
    if not date_header:
        return None
    try:
        return round((parsedate_to_datetime(date_header) - local_utc).total_seconds(), 1)
    except (TypeError, ValueError):
        return None


def _write_summary(out: Path) -> None:
    """Rebuilt from the files in the folder, so a later --only-ws run (e.g. during a print) adds
    its measurement to the summary of the full run."""
    printer_info = _read_json(out / "printer_info.json") or {}
    server_info = _read_json(out / "server_info.json") or {}
    manifest = _read_json(out / "manifest.json") or _read_json(out / "manifest_ws.json") or {}
    objects = (_read_json(out / "objects.json") or {}).get("objects", [])
    status = (_read_json(out / "objects_status.json") or {}).get("status", {})
    if not status:
        for path in sorted(out.glob("ws_estado_inicial_*.json")):
            status = (_read_json(path) or {}).get("status", {}) or status
    measurements = {
        path.stem.removeprefix("ws_medicion_"): data
        for path in sorted(out.glob("ws_medicion_*.json"))
        if (data := _read_json(path))
    }

    now = datetime.now(timezone.utc)
    lines = [
        "# Resumen automático del descubrimiento",
        "",
        f"Regenerado por `backend/scripts/moonraker_discovery.py` el {now:%Y-%m-%d %H:%M} UTC "
        f"({now.astimezone(_COLOMBIA):%Y-%m-%d %H:%M} en Colombia). El análisis hecho a mano está en `README.md`.",
        "",
        f"- Impresora: `{manifest.get('url', '-')}`, host `{printer_info.get('hostname', '-')}`.",
        f"- Klipper `{printer_info.get('software_version', '-')}`; Moonraker `{server_info.get('moonraker_version', '-')}`.",
        f"- Corrida completa: {manifest.get('inicio_utc', '-')} a {manifest.get('fin_utc', '-')} (UTC).",
    ]
    if manifest.get("reloj_impresora_menos_local_s") is not None:
        lines.append(f"- Reloj de la impresora menos reloj local: {manifest['reloj_impresora_menos_local_s']} s.")
    if manifest.get("detenido_por_autenticacion"):
        lines += [
            "",
            f"> **La corrida se detuvo:** la impresora pidió autenticación en `{manifest['detenido_por_autenticacion']}`. "
            "No se intentó ninguna credencial.",
        ]

    lines += ["", "## Pasos", "", "| Paso | Resultado | Detalle |", "|---|---|---|"]
    for name, step in (manifest.get("pasos") or {}).items():
        detail = {key: value for key, value in step.items() if key not in ("ok", "archivos")}
        result = "ok" if step.get("ok") else "fallo o incompleto"
        lines.append(f"| {name} | {result} | {_short(detail, 160).replace('|', '/')} |")

    if objects:
        unknown = [name for name in objects if not _is_standard_module(name)]
        lines += [
            "",
            f"## Objetos de Klipper ({len(objects)})",
            "",
            "Estándar de Klipper: " + ", ".join(f"`{name}`" for name in objects if _is_standard_module(name)) + ".",
            "",
            "No reconocidos (posiblemente propios de Creality): "
            + (", ".join(f"`{name}`" for name in unknown) or "ninguno")
            + ".",
        ]

    for state, data in measurements.items():
        volume = f" (en una impresión de 2 h serían ~{data.get('extrapolacion_2h_mb')} MB)" if state == "printing" else ""
        lines += [
            "",
            f"## Medición del WebSocket con la impresora en `{state}`",
            "",
            f"{data.get('segundos')} s el {data.get('medido_utc', '-')}: {data.get('mensajes')} mensajes, "
            f"{data.get('bytes_por_segundo')} bytes/s{volume}. Intervalo mediano entre actualizaciones de estado: "
            f"{data.get('intervalo_mediano_entre_actualizaciones_s')} s.",
            "",
            "Mensajes por tipo: "
            + ", ".join(f"`{method}` {count}" for method, count in (data.get("por_metodo") or {}).items())
            + ".",
        ]

    if status:
        states = list(measurements)
        lines += [
            "",
            "## Campos (sin las macros)",
            "",
            "| Campo | Valor al consultar | " + " | ".join(f"Hz en `{state}`" for state in states) + " | Rango medido |",
            "|---|---|" + "---|" * len(states) + "---|",
        ]
        for name, value in _flatten({k: v for k, v in status.items() if not k.startswith("gcode_macro ")}):
            rates = [str((measurements[state].get("campos") or {}).get(name, {}).get("hz", 0)) for state in states]
            ranges = []
            for state in states:
                field = (measurements[state].get("campos") or {}).get(name, {})
                if field.get("min") is not None:
                    ranges.append(f"{_short(field['min'])} a {_short(field['max'])}")
            lines.append(f"| `{name}` | {_short(value).replace('|', '/')} | " + " | ".join(rates) + f" | {'; '.join(ranges)} |")

    (out / "resumen_descubrimiento.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


# --- Main ---------------------------------------------------------------------------------------


async def run(args: argparse.Namespace) -> int:
    out: Path = args.out
    out.mkdir(parents=True, exist_ok=True)
    moon = ReadOnlyMoonraker(args.url, args.timeout, args.throttle_kb_s)
    ctx: dict = {"args": args}
    report: dict = {"inicio_utc": _utc_now(), "url": moon.base_url, "solo_lectura": True, "pasos": {}}
    manifest_name = "manifest_ws.json" if args.only_ws else "manifest.json"
    exit_code = 0
    connected = False
    try:
        printer_info = await moon.get_json("/printer/info")
        if printer_info is None:
            # Nothing gathered: keep the files of the previous run untouched.
            print(_UNREACHABLE_HELP.format(url=moon.base_url))
            return 1
        connected = True
        report["reloj_impresora_menos_local_s"] = _clock_offset(moon.first_date_header, datetime.now(timezone.utc))
        _write_json(out / "printer_info.json", printer_info)
        server_info = await moon.get_json("/server/info")
        if server_info is not None:
            _write_json(out / "server_info.json", server_info)
        print(f"Conectado a {moon.base_url} (Klipper {printer_info.get('software_version', '?')}).")

        if not args.only_ws:
            # Perishable evidence first. --steps picks a subset (e.g. everything but the logs).
            steps = {
                "consola_gcode_store": lambda: _save_gcode_store(moon, out),
                "logs": lambda: _save_logs(moon, out, ctx),
                "historial": lambda: _save_history(moon, out, ctx),
                "objetos": lambda: _save_objects(moon, out, ctx),
                "configuracion": lambda: _analyze_config(out, ctx),
                "archivos_gcode": lambda: _save_gcode_files(moon, out, ctx),
                "camaras": lambda: _save_webcams(moon, out, args.skip_webcam_stream),
                "sistema": lambda: _save_machine(moon, out),
            }
            wanted = [name.strip() for name in args.steps.split(",")] if args.steps else list(steps)
            unknown = [name for name in wanted if name not in steps]
            if unknown:
                raise SystemExit(f"Pasos desconocidos: {unknown}. Validos: {list(steps)}")
            for name in wanted:
                await _run_step(report, name, steps[name]())
        if not args.skip_ws:
            await _run_step(report, "medicion_websocket", _measure_websocket(moon, out, ctx, args.ws_seconds))
    except AuthenticationRequired as error:
        report["detenido_por_autenticacion"] = error.url
        print(
            f"\nLa impresora pidio autenticacion en {error.url}.\n"
            "Se detuvo el descubrimiento sin intentar credenciales. Lo reunido hasta aqui quedo guardado."
        )
        exit_code = 2
    finally:
        if connected:
            report["fin_utc"] = _utc_now()
            report["peticiones"] = moon.requests
            _write_json(out / manifest_name, report)
            _write_summary(out)
        await moon.close()

    print(f"\nListo. Resultados en {out} (ver resumen_descubrimiento.md).")
    return exit_code


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Descubrimiento de solo lectura de lo que expone Moonraker/Klipper.")
    parser.add_argument("--url", default="http://192.168.10.22:7125", help="URL de Moonraker (por defecto la Hi-3422)")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT_DIR, help="carpeta de salida")
    parser.add_argument("--ws-seconds", type=float, default=60.0, help="segundos de medicion del WebSocket")
    parser.add_argument("--only-ws", action="store_true", help="solo medir el WebSocket; no descarga nada")
    parser.add_argument("--skip-ws", action="store_true", help="no medir el WebSocket")
    parser.add_argument("--all-logs", action="store_true", help="descargar todos los logs, no solo klippy y moonraker")
    parser.add_argument("--max-log-mb", type=float, default=200.0, help="tope de descarga por log, en MB")
    parser.add_argument("--gcode-file", action="append", default=[], help="archivo G-code extra a revisar (repetible)")
    parser.add_argument("--timeout", type=float, default=15.0, help="timeout por peticion, en segundos")
    parser.add_argument("--ws-skip-macros", action="store_true", help="en la medicion del WebSocket, no suscribirse a las macros (gcode_macro *): menos carga durante una impresion")
    parser.add_argument("--throttle-kb-s", type=float, default=None, help="limite de velocidad de descarga, en KB/s (para usarlo durante una impresion)")
    parser.add_argument("--steps", default="", help="pasos a correr, separados por coma (por defecto todos): consola_gcode_store,logs,historial,objetos,configuracion,archivos_gcode,camaras,sistema")
    parser.add_argument("--skip-webcam-stream", action="store_true", help="de las camaras, solo la lista y un cuadro (snapshot); no leer el stream")
    args = parser.parse_args()
    if args.only_ws and args.skip_ws:
        parser.error("--only-ws y --skip-ws se excluyen")
    return args


def main() -> None:
    sys.exit(asyncio.run(run(parse_args())))


if __name__ == "__main__":
    main()
