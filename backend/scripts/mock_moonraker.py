"""Simulated Klipper/Moonraker printer, for testing PrintWatch without the real Creality Hi.

Implements the parts of the Moonraker API this project touches: the read endpoints used by the
discovery script and the telemetry listener, the WebSocket subscription protocol (updates every
250 ms carrying only the fields that changed, like Klipper), print control (start/pause/resume/
cancel) so the auto-pause can be exercised without risking a real print, and a G-code console
that understands the commands an operator would type in Fluidd (temperatures, speed and flow
factors, fan, babystepping, exclude object), so external interventions can be simulated.

Field shapes follow upstream Klipper's status reference plus the Creality quirks measured on the
Hi-3422: print_stats.info.current_layer stays null, the layer comes from virtual_sdcard.layer and
layer_count, the layer height from virtual_sdcard.cur_print_data.metadata, print_stats.z_pos lags,
and errors arrive as a JSON string with a "key" code in print_stats.message. Everything else (bed
size, temperatures, macros, the camera image) is a plausible stand-in, not a measurement.

Usage:
    backend\\.venv\\Scripts\\python.exe backend\\scripts\\mock_moonraker.py --port 7125 --auto-start
    curl.exe -X POST "http://localhost:7125/printer/print/start?filename=mock_box.gcode"
    curl.exe -X POST "http://localhost:7125/printer/gcode/script?script=M104%20S245"   (external change)
    curl.exe -X POST "http://localhost:7125/mock/error"                                (Klipper error)
"""

import argparse
import asyncio
import io
import json
import logging
import math
import random
import re
import time
from collections import deque
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime

import uvicorn
from fastapi import FastAPI, Request, Response, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse, StreamingResponse
from PIL import Image, ImageDraw

BED_X_MM = 260.0
BED_Y_MM = 260.0
MAX_Z_MM = 300.0
STATUS_INTERVAL_SECONDS = 0.25  # Klipper batches subscription updates every 250 ms
TICK_SECONDS = 0.05
LOOKAHEAD_SECONDS = 0.25  # toolhead.position is the end of the queued move, ahead of the nozzle
FILAMENT_PER_MM = 0.0333  # 0.4 x 0.2 mm bead from 1.75 mm filament
FIRST_LAYER_HEIGHT = 0.2
PARK_X, PARK_Y = 10.0, 250.0
Z_POS_LAG_LAYERS = 5  # Creality's print_stats.z_pos only catches up every few layers
MOCK_FILE = "mock_box.gcode"
EXTRUDER_TARGET = 240.0
SECOND_LAYER_EXTRUDER_TARGET = 235.0  # the file's "M104 S235" at layer 2, like a slicer's first-layer bump
BED_TARGET = 70.0
CAMERA_SIZE = (640, 480)
# The simulated camera: a pinhole camera in front of the printer, looking down at the bed. On a
# bed-slinger the nozzle stays at a fixed world Y and the bed slides under it, so a camera fixed
# to the frame sees the bed move with the toolhead's Y (unless camera_on_bed). These are the ground
# truth the bed-map tests check against.
CAMERA_POSITION = (130.0, -230.0, 300.0)  # mm, world coordinates
CAMERA_LOOK_AT = (130.0, 130.0, 0.0)
CAMERA_FOCAL_PX = 560.0
NOZZLE_WORLD_Y = 130.0  # world Y of the nozzle; bed and world coincide when toolhead Y is this

logger = logging.getLogger("mock_moonraker")


class GcodeError(Exception):
    pass


@dataclass
class PrintObject:
    name: str
    center: tuple[float, float]
    size: float  # square side, mm

    @property
    def polygon(self) -> list[list[float]]:
        cx, cy = self.center
        half = self.size / 2
        return [[cx - half, cy - half], [cx + half, cy - half], [cx + half, cy + half], [cx - half, cy + half]]


class Heater:
    def __init__(self, tau: float, ambient: float = 25.0) -> None:
        self.tau = tau
        self.ambient = ambient
        self.temperature = ambient
        self.target = 0.0
        self.power = 0.0
        # PWM needed to hold the target; /mock/heater raises it to simulate wear or a draught.
        self.hold_power = 0.3

    def step(self, dt: float) -> None:
        goal = self.target if self.target > 0 else self.ambient
        # Cooling with the heater off is much slower than heating.
        tau = self.tau if goal >= self.temperature else self.tau * 4
        self.temperature += (goal - self.temperature) * (1 - math.exp(-dt / tau))
        if self.target > 0:
            self.power = min(1.0, max(0.0, self.hold_power + (self.target - self.temperature) / 15))
        else:
            self.power = 0.0

    def status(self, noise: float) -> dict:
        return {"temperature": round(self.temperature + noise, 2), "target": self.target, "power": round(self.power, 3)}


class LayerPath:
    """One layer's toolpath: each object's perimeter plus a few infill lines, with travel moves in
    between. Positions are looked up by distance travelled along the path."""

    def __init__(self, objects: list[PrintObject]) -> None:
        self.segments: list[tuple[tuple[float, float], tuple[float, float], str | None]] = []
        position = None
        for obj in objects:
            corners = [tuple(point) for point in obj.polygon]
            if position is not None:
                self.segments.append((position, corners[0], None))
            for start, end in zip(corners, corners[1:] + corners[:1]):
                self.segments.append((start, end, obj.name))
            position = corners[0]
            cx, cy = obj.center
            half = obj.size / 2 - 1
            for index, fraction in enumerate((0.2, 0.4, 0.6, 0.8)):
                y = cy - obj.size / 2 + fraction * obj.size
                start, end = ((cx - half, y), (cx + half, y)) if index % 2 == 0 else ((cx + half, y), (cx - half, y))
                self.segments.append((position, start, None))
                self.segments.append((start, end, obj.name))
                position = end

        self.lengths = [math.dist(start, end) for start, end, _ in self.segments]
        self.total = sum(self.lengths)

    def point_at(self, distance: float) -> tuple[float, float, str | None]:
        if not self.segments:
            return PARK_X, PARK_Y, None
        for (start, end, name), length in zip(self.segments, self.lengths):
            if distance <= length:
                ratio = distance / length if length else 0.0
                return start[0] + (end[0] - start[0]) * ratio, start[1] + (end[1] - start[1]) * ratio, name
            distance -= length
        end = self.segments[-1][1]
        return end[0], end[1], self.segments[-1][2]

    def extruded_until(self, distance: float) -> float:
        extruded = 0.0
        for (_, _, name), length in zip(self.segments, self.lengths):
            step = min(distance, length)
            if name is not None:
                extruded += step
            distance -= step
            if distance <= 0:
                break
        return extruded


def _normalize(vector: tuple[float, float, float]) -> tuple[float, float, float]:
    length = math.sqrt(sum(component * component for component in vector))
    return tuple(component / length for component in vector)


def _cross(a: tuple[float, float, float], b: tuple[float, float, float]) -> tuple[float, float, float]:
    return a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]


def _camera_axes() -> tuple[tuple, tuple, tuple]:
    """Camera frame (x right, y down, z forward) in world coordinates, for CAMERA_LOOK_AT."""
    forward = _normalize(tuple(t - p for t, p in zip(CAMERA_LOOK_AT, CAMERA_POSITION)))
    right = _normalize(_cross(forward, (0.0, 0.0, 1.0)))
    down = _cross(forward, right)
    return right, down, forward


_CAMERA_AXES = _camera_axes()
camera_on_bed = False


def camera_project(bed_x: float, bed_y: float, z: float, toolhead_y: float) -> tuple[float, float] | None:
    """Pixel where the simulated camera sees the bed point (bed_x, bed_y) at height z, with the
    toolhead at toolhead_y. None if the point is behind the camera."""
    world_y = bed_y if camera_on_bed else bed_y + (NOZZLE_WORLD_Y - toolhead_y)
    offset = (bed_x - CAMERA_POSITION[0], world_y - CAMERA_POSITION[1], z - CAMERA_POSITION[2])
    x, y, depth = (sum(a * b for a, b in zip(axis, offset)) for axis in _CAMERA_AXES)
    if depth <= 1.0:
        return None
    return CAMERA_FOCAL_PX * x / depth + CAMERA_SIZE[0] / 2, CAMERA_FOCAL_PX * y / depth + CAMERA_SIZE[1] / 2


class SimulatedPrinter:
    def __init__(
        self, layers: int, layer_seconds: float, layer_height: float, seed: int, heater_tau_scale: float = 1.0
    ) -> None:
        self.rng = random.Random(seed)
        self.boot_monotonic = time.monotonic()
        self.boot_wall = time.time()
        self.layer_count = layers
        self.layer_seconds = layer_seconds
        self.layer_height = layer_height
        self.objects = [PrintObject("BOX_1", (95.0, 130.0), 50.0), PrintObject("BOX_2", (165.0, 130.0), 50.0)]
        self.nominal_speed = LayerPath(self.objects).total / layer_seconds
        self.excluded: list[str] = []
        self._path = LayerPath(self.objects)

        # heater_tau_scale < 1 makes heating near-instant, for tests.
        self.extruder = Heater(tau=3.0 * heater_tau_scale)
        self.bed = Heater(tau=6.0 * heater_tau_scale)
        self.fan_speed = 0.0
        self.speed_factor = 1.0
        self.extrude_factor = 1.0
        self.homing_origin = [0.0, 0.0, 0.0, 0.0]
        self.homed_axes = ""
        self.filament_detected = True

        self.state = "standby"
        self.message = ""
        self.filename = ""
        self.layer = 0
        self.distance = 0.0
        self.position = [PARK_X, PARK_Y, 10.0]  # nozzle x, y, z in toolhead coordinates
        self.saved_position: list[float] | None = None
        self.e = 0.0
        self.filament_used = 0.0
        self.print_duration = 0.0
        self.total_duration = 0.0
        self.reported_z = 0.0
        self.current_object: str | None = None
        self.velocity = 0.0
        self.extruder_velocity = 0.0

        self._gcode_cache: bytes | None = None
        self.gcode_store: deque = deque(maxlen=1000)  # Moonraker's default gcode_store_size
        self.history: list[dict] = []
        self._job_counter = 0
        self.klippy_log: deque = deque(maxlen=50000)
        self.moonraker_log: deque = deque(maxlen=50000)
        self.outbox: asyncio.Queue = asyncio.Queue()
        self.cputime = 0.0
        self.mcu_stats = {"bytes_write": 0, "bytes_read": 0, "send_seq": 0, "receive_seq": 0}
        self._last_stats_log = 0.0
        self._last_noise: dict[str, float] = {}
        self._add_past_job()
        self.log_klippy(
            f"Start printer at {time.ctime()} ({time.time():.1f} {self.eventtime():.1f})\n"
            "Mock Klipper (backend/scripts/mock_moonraker.py), not a real printer log"
        )

    # --- Clock and logs ---

    def eventtime(self) -> float:
        # Klipper's monotonic clock; offset so it doesn't look like the printer just booted.
        return round(time.monotonic() - self.boot_monotonic + 1000.0, 3)

    def log_klippy(self, text: str) -> None:
        self.klippy_log.extend(text.splitlines())

    def log_moonraker(self, text: str) -> None:
        stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S,%f")[:-3]
        self.moonraker_log.append(f"{stamp} {text}")

    def notify(self, method: str, params: list) -> None:
        self.outbox.put_nowait({"jsonrpc": "2.0", "method": method, "params": params})

    def respond(self, text: str) -> None:
        self.gcode_store.append({"message": text, "time": time.time(), "type": "response"})
        self.notify("notify_gcode_response", [text])

    # --- Files and history ---

    def gcode_bytes(self) -> bytes:
        if self._gcode_cache is None:
            self._build_gcode()
        return self._gcode_cache

    def _build_gcode(self) -> None:
        """Generates the file and remembers the byte offsets of START_PRINT, each layer and
        END_PRINT, so the reported file_position walks through the file like Klipper's does."""
        lines, markers = self._gcode_lines()
        offsets, position = [], 0
        for line in lines:
            offsets.append(position)
            position += len(line.encode()) + 1
        self._gcode_cache = "\n".join(lines).encode()
        self._start_offset = offsets[markers["start"]]
        self._end_offset = offsets[markers["end"]]
        self._layer_offsets = {layer: offsets[index] for layer, index in markers.items() if isinstance(layer, int)}
        self._layer_offsets[self.layer_count + 1] = self._end_offset

    def _gcode_lines(self) -> tuple[list[str], dict]:
        lines = [
            "; generated by MockSlicer 1.0 - synthetic file for PrintWatch tests, not a real print",
            f"; layer_height = {self.layer_height}",
            f"; first_layer_height = {FIRST_LAYER_HEIGHT}",
            "; filament_type = PETG",
        ]
        markers: dict = {}
        for obj in self.objects:
            polygon = json.dumps([[round(x, 3), round(y, 3)] for x, y in obj.polygon], separators=(",", ":"))
            lines.append(
                f"EXCLUDE_OBJECT_DEFINE NAME={obj.name} CENTER={obj.center[0]:.3f},{obj.center[1]:.3f} POLYGON={polygon}"
            )
        markers["start"] = len(lines)
        lines.append(f"START_PRINT EXTRUDER_TEMP={EXTRUDER_TARGET:.0f} BED_TEMP={BED_TARGET:.0f}")
        path = LayerPath(self.objects)
        e = 0.0
        for layer in range(1, self.layer_count + 1):
            z = FIRST_LAYER_HEIGHT + (layer - 1) * self.layer_height
            markers[layer] = len(lines)
            lines += [";LAYER_CHANGE", f";Z:{z:.2f}", f"G1 Z{z:.2f} F600"]
            # Programmed changes, applied by _start_layer at the same point of the print.
            if layer == 2:
                lines.append(f"M104 S{SECOND_LAYER_EXTRUDER_TARGET:.0f}")
            if layer == 3:
                lines.append("M106 S128")
            current = None
            for (start, end, name), length in zip(path.segments, path.lengths):
                if name != current:
                    if current is not None:
                        lines.append(f"EXCLUDE_OBJECT_END NAME={current}")
                    if name is not None:
                        lines.append(f"EXCLUDE_OBJECT_START NAME={name}")
                    current = name
                if name is None:
                    lines.append(f"G0 X{end[0]:.3f} Y{end[1]:.3f} F9000")
                else:
                    e += length * FILAMENT_PER_MM
                    lines.append(f"G1 X{end[0]:.3f} Y{end[1]:.3f} E{e:.5f} F6000")
            if current is not None:
                lines.append(f"EXCLUDE_OBJECT_END NAME={current}")
        markers["end"] = len(lines)
        lines += ["END_PRINT", ""]
        return lines, markers

    def file_metadata(self, filename: str) -> dict | None:
        if filename != MOCK_FILE:
            return None
        size = len(self.gcode_bytes())
        object_height = FIRST_LAYER_HEIGHT + (self.layer_count - 1) * self.layer_height
        return {
            "filename": filename,
            "size": size,
            "modified": self.boot_wall - 3600,
            "slicer": "MockSlicer",
            "slicer_version": "1.0",
            "layer_height": self.layer_height,
            "first_layer_height": FIRST_LAYER_HEIGHT,
            "object_height": round(object_height, 2),
            "estimated_time": round(self.layer_count * self.layer_seconds),
            "filament_total": round(LayerPath(self.objects).extruded_until(math.inf) * FILAMENT_PER_MM * self.layer_count, 2),
            "filament_type": "PETG",
            "nozzle_diameter": 0.4,
            "first_layer_extr_temp": EXTRUDER_TARGET,
            "first_layer_bed_temp": BED_TARGET,
            "gcode_start_byte": self._start_offset,
            "gcode_end_byte": self._end_offset,
            "thumbnails": [],
        }

    def _add_past_job(self) -> None:
        self._job_counter += 1
        end = self.boot_wall - 1800
        duration = self.layer_count * self.layer_seconds
        self.history.append(
            {
                "job_id": f"{self._job_counter:06X}",
                "exists": True,
                "end_time": end,
                "filament_used": 812.4,
                "filename": MOCK_FILE,
                "metadata": self.file_metadata(MOCK_FILE),
                "print_duration": duration,
                "status": "completed",
                "start_time": end - duration - 60,
                "total_duration": duration + 60,
                "user": "_TRUSTED_USER_",
                "auxiliary_data": [],
            }
        )

    def _current_job(self) -> dict | None:
        return self.history[-1] if self.history and self.history[-1]["status"] == "in_progress" else None

    def _finish_job(self, status: str) -> None:
        job = self._current_job()
        if job is None:
            return
        job.update(
            status=status,
            end_time=time.time(),
            filament_used=round(self.filament_used, 3),
            print_duration=round(self.print_duration, 3),
            total_duration=round(self.total_duration, 3),
        )
        self.notify("notify_history_changed", [{"action": "finished", "job": job}])

    # --- Print control ---

    def start(self, filename: str) -> None:
        if self.state in ("printing", "paused"):
            raise GcodeError("Print already in progress")
        if self.file_metadata(filename) is None:
            raise GcodeError(f"File not found: {filename}")
        self.filename = filename
        self.state = "printing"
        self.message = ""
        self.layer = 0
        self.distance = 0.0
        self.e = 0.0
        self.filament_used = 0.0
        self.print_duration = 0.0
        self.total_duration = 0.0
        self.reported_z = 0.0
        self.excluded = []
        self._path = LayerPath(self.objects)
        self.homed_axes = "xyz"
        self.position = [5.0, 5.0, 5.0]
        # What the file's START_PRINT EXTRUDER_TEMP=240 BED_TEMP=70 does through the macro.
        self.extruder.target = EXTRUDER_TARGET
        self.bed.target = BED_TARGET
        self._job_counter += 1
        job = {
            "job_id": f"{self._job_counter:06X}",
            "exists": True,
            "end_time": None,
            "filament_used": 0.0,
            "filename": filename,
            "metadata": self.file_metadata(filename),
            "print_duration": 0.0,
            "status": "in_progress",
            "start_time": time.time(),
            "total_duration": 0.0,
            "user": "_TRUSTED_USER_",
            "auxiliary_data": [],
        }
        self.history.append(job)
        self.notify("notify_history_changed", [{"action": "added", "job": job}])
        self.log_klippy(f"Starting SD card print (position 0)\nvirtual_sdcard: printing {filename}")

    def pause(self) -> None:
        if self.state == "paused":
            raise GcodeError("Print already paused")
        if self.state != "printing":
            raise GcodeError("Print is not in progress")
        self.state = "paused"
        # What a typical PAUSE macro does: lift Z and park the head out of the way.
        self.saved_position = list(self.position)
        self.position = [PARK_X, PARK_Y, min(MAX_Z_MM, self.position[2] + 10.0)]
        self.log_klippy(f"Exiting SD card print (position {self._file_position()})")
        self.respond("// action:paused")

    def resume(self) -> None:
        if self.state != "paused":
            raise GcodeError("Print is not paused, resume aborted")
        self.state = "printing"
        if self.saved_position is not None:
            self.position = self.saved_position
            self.saved_position = None
        self.log_klippy("Starting SD card print (resume)")
        self.respond("// action:resumed")

    def cancel(self) -> None:
        if self.state not in ("printing", "paused"):
            raise GcodeError("No print in progress")
        self.state = "cancelled"
        self._end_print()
        self.log_klippy(f"Exiting SD card print (position {self._file_position()})")
        self._finish_job("cancelled")
        self.respond("// action:cancel")

    def fail(self, x: float, y: float, z: float) -> None:
        """A Klipper error mid-print, reported the way the Hi-3422 did on 2026-09-25."""
        if self.state not in ("printing", "paused"):
            raise GcodeError("No print in progress")
        message = f"Move out of range: {x:.3f} {y:.3f} {z:.3f} [{self.e:.3f}]"
        self.state = "error"
        self.message = json.dumps({"code": "key243", "msg": message, "values": [x, y, z, round(self.e, 3)]})
        self.velocity = self.extruder_velocity = 0.0
        self.log_klippy(f"{message}\nExiting SD card print (position {self._file_position()})")
        self._finish_job("error")
        self.respond(f"!! {message}")

    def _end_print(self) -> None:
        self.extruder.target = self.bed.target = 0.0
        self.fan_speed = 0.0
        self.velocity = self.extruder_velocity = 0.0
        self.current_object = None
        self.position = [PARK_X, PARK_Y, min(MAX_Z_MM, self.position[2] + 10.0)]

    def _file_position(self) -> int:
        """Like Klipper's virtual_sdcard.file_position: the start of the line being executed.
        While heating that is START_PRINT (its M190/M109 block); then it walks through each
        layer's lines; at the end it is the end of the file."""
        size = len(self.gcode_bytes())
        if self.state == "complete":
            return size
        if self.layer == 0:
            return self._start_offset
        start = self._layer_offsets[self.layer]
        end = self._layer_offsets.get(self.layer + 1, self._end_offset)
        fraction = min(1.0, self.distance / max(self._path.total, 1e-6))
        return int(start + fraction * (end - start))

    # --- G-code console ---

    def run_gcode(self, script: str) -> None:
        """A script from the console API: stored in gcode_store, like Moonraker does."""
        for raw_line in script.splitlines():
            line = raw_line.split(";", 1)[0].strip()
            if not line:
                continue
            self.gcode_store.append({"message": line, "time": time.time(), "type": "command"})
            try:
                self._run_command(line)
            except GcodeError as error:
                self.respond(f"!! {error}")
                raise

    def run_from_screen(self, script: str) -> None:
        """A change made on the printer's own screen: same effect, but nothing reaches the console
        log - the case the event log can only call "external"."""
        for raw_line in script.splitlines():
            line = raw_line.split(";", 1)[0].strip()
            if line:
                self._run_command(line)

    @staticmethod
    def _param(line: str, name: str) -> str | None:
        match = re.search(rf"\b{name}=?(\S+)", line, re.IGNORECASE)
        return match.group(1) if match else None

    def _float_param(self, line: str, name: str) -> float:
        value = self._param(line, name)
        try:
            return float(value)
        except (TypeError, ValueError):
            raise GcodeError(f"Malformed command '{line}'") from None

    def _run_command(self, line: str) -> None:
        command = line.split()[0].upper()
        if command in ("M104", "M109"):
            self.extruder.target = self._float_param(line, "S")
        elif command in ("M140", "M190"):
            self.bed.target = self._float_param(line, "S")
        elif command == "SET_HEATER_TEMPERATURE":
            heater = (self._param(line, "HEATER") or "").lower()
            target = self._float_param(line, "TARGET")
            if heater == "extruder":
                self.extruder.target = target
            elif heater == "heater_bed":
                self.bed.target = target
            else:
                raise GcodeError(f"Unknown heater '{heater}'")
        elif command == "M220":
            self.speed_factor = self._float_param(line, "S") / 100
        elif command == "M221":
            self.extrude_factor = self._float_param(line, "S") / 100
        elif command == "M106":
            self.fan_speed = min(1.0, max(0.0, self._float_param(line, "S") / 255))
        elif command == "M107":
            self.fan_speed = 0.0
        elif command == "SET_GCODE_OFFSET":
            if self._param(line, "Z_ADJUST") is not None:
                self.homing_origin[2] = round(self.homing_origin[2] + self._float_param(line, "Z_ADJUST"), 4)
            elif self._param(line, "Z") is not None:
                self.homing_origin[2] = self._float_param(line, "Z")
        elif command == "EXCLUDE_OBJECT":
            name = self._param(line, "NAME")
            if name is None:
                self.respond("// Excluded objects: " + " ".join(self.excluded))
                return
            if name not in [obj.name for obj in self.objects]:
                raise GcodeError(f"Unknown object: {name}")
            if name not in self.excluded:
                self.excluded.append(name)
                self._rebuild_path()
            self.respond(f"// Excluding object {name}")
        elif command == "PAUSE":
            self.pause()
        elif command == "RESUME":
            self.resume()
        elif command == "CANCEL_PRINT":
            self.cancel()
        elif command in ("G28", "G0", "G1", "G90", "G91", "G92", "M400", "M84", "M18", "M115", "M114"):
            # Accepted so the console behaves, but the mock's motion only follows the print.
            pass
        else:
            raise GcodeError(f'Unknown command:"{command}"')

    def _rebuild_path(self) -> None:
        # Keep the head where it is along the shortened path.
        progress = self.distance / max(self._path.total, 1e-6)
        self._path = LayerPath([obj for obj in self.objects if obj.name not in self.excluded])
        self.distance = progress * self._path.total

    # --- Simulation ---

    def tick(self, dt: float) -> None:
        self.extruder.step(dt)
        self.bed.step(dt)
        self.cputime += dt * 0.3
        self.mcu_stats["bytes_write"] += 120
        self.mcu_stats["bytes_read"] += 400
        self.mcu_stats["send_seq"] += 3
        self.mcu_stats["receive_seq"] += 3

        if self.state == "paused":
            self.total_duration += dt
            self.velocity = self.extruder_velocity = 0.0
        elif self.state == "printing":
            self.total_duration += dt
            if self.layer == 0:
                self._heat_up()
            else:
                self._advance(dt)

        now = self.eventtime()
        if self.state == "printing" and now - self._last_stats_log >= 1.0:
            self._last_stats_log = now
            self.log_klippy(
                f"Stats {now:.1f}: gcodein=0 mcu: mcu_awake=0.004 mcu_task_avg=0.000012 "
                f"bytes_write={self.mcu_stats['bytes_write']} bytes_read={self.mcu_stats['bytes_read']} "
                f"print_time={self.print_duration:.3f} extruder: target={self.extruder.target:.0f} "
                f"temp={self.extruder.temperature:.1f} pwm={self.extruder.power:.3f} heater_bed: "
                f"target={self.bed.target:.0f} temp={self.bed.temperature:.1f} pwm={self.bed.power:.3f}"
            )

    def _heat_up(self) -> None:
        self.velocity = self.extruder_velocity = 0.0
        if self.extruder.temperature > self.extruder.target - 3 and self.bed.temperature > self.bed.target - 3:
            self._start_layer(1)

    def _start_layer(self, layer: int) -> None:
        self.layer = layer
        self.distance = 0.0
        # The changes programmed in the file at the start of these layers (see _gcode_lines).
        if layer == 2:
            self.extruder.target = SECOND_LAYER_EXTRUDER_TARGET
        if layer == 3:
            self.fan_speed = 128 / 255
        if layer % Z_POS_LAG_LAYERS == 1:
            self.reported_z = round(FIRST_LAYER_HEIGHT + (layer - 1) * self.layer_height, 3)

    def _advance(self, dt: float) -> None:
        self.print_duration += dt
        speed = self.nominal_speed * self.speed_factor
        before = self.distance
        self.distance += speed * dt
        extruded = self._path.extruded_until(self.distance) - self._path.extruded_until(before)
        filament = extruded * FILAMENT_PER_MM * self.extrude_factor
        self.e += filament
        self.filament_used += filament
        self.velocity = speed
        self.extruder_velocity = filament / dt if dt else 0.0

        if self.distance >= self._path.total:
            if self.layer >= self.layer_count:
                self.state = "complete"
                self._end_print()
                self.log_klippy(f"Exiting SD card print (position {self._file_position()})\nFinished SD card print")
                self._finish_job("completed")
                self.respond("// Done printing file")
                return
            self._start_layer(self.layer + 1)

        x, y, name = self._path.point_at(self.distance)
        z = FIRST_LAYER_HEIGHT + (self.layer - 1) * self.layer_height + self.homing_origin[2]
        self.position = [x, y, z]
        self.current_object = name

    # --- Status (Klipper objects) ---

    def _noise(self, key: str, scale: float) -> float:
        # Sensor noise, fixed per status round so every client sees the same value.
        return self._last_noise.setdefault(key, self.rng.gauss(0, scale))

    def _commanded_position(self) -> list[float]:
        if self.state != "printing" or self.layer == 0:
            return [*self.position, self.e]
        ahead = self.distance + self.nominal_speed * self.speed_factor * LOOKAHEAD_SECONDS
        x, y, _ = self._path.point_at(min(ahead, self._path.total))
        return [x, y, self.position[2], self.e]

    def _bed_mesh(self) -> dict:
        points = [
            [round(0.08 * math.sin(x / 60) + 0.05 * math.cos(y / 45) - 0.03, 4) for x in range(10, 251, 60)]
            for y in range(10, 251, 60)
        ]
        params = {"min_x": 10.0, "max_x": 250.0, "min_y": 10.0, "max_y": 250.0, "x_count": 5, "y_count": 5,
                  "mesh_x_pps": 2, "mesh_y_pps": 2, "algo": "bicubic", "tension": 0.2}
        return {
            "profile_name": "default",
            "mesh_min": [10.0, 10.0],
            "mesh_max": [250.0, 250.0],
            "probed_matrix": points,
            "mesh_matrix": points,
            "profiles": {"default": {"points": points, "mesh_params": params}},
        }

    def _status_builders(self) -> dict:
        printing = self.state == "printing" and self.layer > 0
        commanded = self._commanded_position()
        gcode_position = [round(a - b, 4) for a, b in zip(commanded, self.homing_origin)]
        metadata = self.file_metadata(self.filename) if self.filename else None
        progress = 0.0
        if self.filename and self.state in ("printing", "paused") and self.layer > 0:
            progress = round(self._file_position() / metadata["size"], 4)
        elif self.state == "complete":
            progress = 1.0
        return {
            "webhooks": lambda: {"state": "ready", "state_message": "Printer is ready"},
            "configfile": self._configfile,
            "mcu": lambda: {
                "mcu_version": "mock-mcu",
                "mcu_build_versions": "mock",
                "mcu_constants": {"MCU": "mock", "CLOCK_FREQ": 64000000},
                "last_stats": {**self.mcu_stats, "mcu_awake": 0.004, "mcu_task_avg": 1.2e-05, "bytes_retransmit": 9,
                               "srtt": 0.001, "rttvar": 0.0005, "rto": 0.025, "freq": 64000000},
            },
            "heaters": lambda: {
                "available_heaters": ["heater_bed", "extruder"],
                "available_sensors": ["temperature_sensor mcu_temp", "heater_bed", "extruder"],
                "available_monitors": [],
            },
            "gcode_move": lambda: {
                "speed_factor": self.speed_factor,
                "speed": 6000.0,  # last G1 F value, mm/min
                "extrude_factor": self.extrude_factor,
                "absolute_coordinates": True,
                "absolute_extrude": True,
                "homing_origin": list(self.homing_origin),
                "position": [round(value, 4) for value in commanded],
                "gcode_position": gcode_position,
            },
            "toolhead": lambda: {
                "homed_axes": self.homed_axes,
                "axis_minimum": [-2.0, -2.0, -2.0, 0.0],
                "axis_maximum": [BED_X_MM, BED_Y_MM, MAX_Z_MM, 0.0],
                "print_time": round(self.print_duration + 1.5, 3),
                "stalls": 0,
                "estimated_print_time": round(self.print_duration + 1.2, 3),
                "extruder": "extruder",
                "position": [round(value, 4) for value in commanded],
                "max_velocity": 500.0,
                "max_accel": 12000.0,
                "minimum_cruise_ratio": 0.5,
                "square_corner_velocity": 5.0,
            },
            "motion_report": lambda: {
                "live_position": [round(value, 4) for value in (*self.position, self.e)],
                "live_velocity": round(self.velocity, 3),
                "live_extruder_velocity": round(self.extruder_velocity, 4),
                "steppers": ["extruder", "stepper_x", "stepper_y", "stepper_z"],
                "trapq": ["extruder", "toolhead"],
            },
            "extruder": lambda: {
                **self.extruder.status(self._noise("extruder", 0.08)),
                "can_extrude": self.extruder.temperature >= 170,
                "pressure_advance": 0.04,
                "smooth_time": 0.04,
                "motion_queue": None,
            },
            "heater_bed": lambda: self.bed.status(self._noise("bed", 0.04)),
            "fan": lambda: {"speed": self.fan_speed, "rpm": None},
            "heater_fan hotend_fan": lambda: {"speed": 1.0 if self.extruder.temperature > 50 else 0.0, "rpm": None},
            "temperature_sensor mcu_temp": lambda: {
                "temperature": round(41.0 + self._noise("mcu_temp", 0.3), 2),
                "measured_min_temp": 38.2,
                "measured_max_temp": 46.9,
            },
            "filament_switch_sensor filament_sensor": lambda: {
                "filament_detected": self.filament_detected,
                "enabled": True,
            },
            "idle_timeout": lambda: {
                "state": "Printing" if self.state == "printing" else "Ready",
                "printing_time": round(self.total_duration, 3) if self.state in ("printing", "paused") else 0.0,
            },
            "display_status": lambda: {"progress": progress, "message": None},
            "pause_resume": lambda: {"is_paused": self.state == "paused"},
            "print_stats": lambda: {
                "filename": self.filename,
                "total_duration": round(self.total_duration, 6),
                "print_duration": round(self.print_duration, 6),
                "filament_used": round(self.filament_used, 6),
                "state": self.state,
                "message": self.message,
                "info": {"total_layer": None, "current_layer": None},
                "z_pos": self.reported_z,
            },
            "virtual_sdcard": lambda: {
                "file_path": f"/home/mock/printer_data/gcodes/{self.filename}" if self.filename else None,
                "progress": progress,
                "is_active": printing,
                "file_position": self._file_position() if self.filename else 0,
                "file_size": metadata["size"] if metadata else 0,
                "layer": self.layer,
                "layer_count": self.layer_count if self.filename else 0,
                "cur_print_data": {"metadata": metadata} if metadata else {},
            },
            "exclude_object": lambda: {
                "objects": [
                    {"name": obj.name, "center": list(obj.center), "polygon": obj.polygon} for obj in self.objects
                ]
                if self.filename
                else [],
                "excluded_objects": list(self.excluded),
                "current_object": self.current_object if printing else None,
            },
            "bed_mesh": self._bed_mesh,
            "system_stats": lambda: {
                "sysload": round(0.8 + self._noise("sysload", 0.05), 2),
                "cputime": round(self.cputime, 3),
                "memavail": 712000,
            },
            "stepper_enable": lambda: {
                "steppers": {name: bool(self.homed_axes) for name in ("stepper_x", "stepper_y", "stepper_z", "extruder")}
            },
            "gcode_macro PAUSE": dict,
            "gcode_macro RESUME": dict,
            "gcode_macro CANCEL_PRINT": dict,
            "gcode_macro START_PRINT": dict,
            "gcode_macro END_PRINT": dict,
        }

    def object_names(self) -> list[str]:
        return list(self._status_builders())

    def status(self, request: dict[str, list[str] | None]) -> dict:
        """Status for {object: fields or None}; unknown objects are left out, as in Klipper."""
        builders = self._status_builders()
        result = {}
        for name, fields in request.items():
            builder = builders.get(name)
            if builder is None:
                continue
            values = builder()
            result[name] = {key: values[key] for key in fields if key in values} if fields else values
        return result

    def new_noise_round(self) -> None:
        self._last_noise = {}

    def _configfile(self) -> dict:
        config = {
            "printer": {"kinematics": "cartesian", "max_velocity": "500", "max_accel": "12000"},
            "stepper_x": {"position_min": "-2", "position_max": str(BED_X_MM), "position_endstop": "-2"},
            "stepper_y": {"position_min": "-2", "position_max": str(BED_Y_MM), "position_endstop": "-2"},
            "stepper_z": {"position_min": "-2", "position_max": str(MAX_Z_MM)},
            "extruder": {"nozzle_diameter": "0.400", "filament_diameter": "1.750", "max_temp": "300"},
            "heater_bed": {"max_temp": "110"},
            "bed_mesh": {"mesh_min": "10,10", "mesh_max": "250,250", "probe_count": "5,5"},
            "exclude_object": {},
            "virtual_sdcard": {"path": "/home/mock/printer_data/gcodes"},
            "gcode_macro PAUSE": {
                "rename_existing": "BASE_PAUSE",
                "gcode": "\nSAVE_GCODE_STATE NAME=PAUSE_state\nBASE_PAUSE\nG91\nG1 Z10 F600\nG90\nG1 X10 Y250 F6000",
            },
            "gcode_macro RESUME": {
                "rename_existing": "BASE_RESUME",
                "gcode": "\nRESTORE_GCODE_STATE NAME=PAUSE_state MOVE=1 MOVE_SPEED=100\nBASE_RESUME",
            },
            "gcode_macro CANCEL_PRINT": {
                "rename_existing": "BASE_CANCEL_PRINT",
                "gcode": "\nTURN_OFF_HEATERS\nM107\nBASE_CANCEL_PRINT",
            },
            "gcode_macro START_PRINT": {"gcode": "\nG28\nM190 S{params.BED_TEMP}\nM109 S{params.EXTRUDER_TEMP}"},
            "gcode_macro END_PRINT": {"gcode": "\nTURN_OFF_HEATERS\nM107\nG91\nG1 Z10 F600\nG90\nG1 X10 Y250 F6000\nM84"},
        }

        def parse(value: str):
            if "\n" in value or not value:
                return value
            parts = value.split(",")
            try:
                numbers = [float(part) for part in parts]
            except ValueError:
                return value.lower() if value.isalpha() else value
            return numbers if len(numbers) > 1 else numbers[0]

        settings = {
            name.lower(): {key: parse(value) for key, value in section.items()} for name, section in config.items()
        }
        return {
            "config": config,
            "settings": settings,
            "warnings": [],
            "save_config_pending": False,
            "save_config_pending_items": {},
        }


# --- Camera ----------------------------------------------------------------------------------------

def render_camera(printer: SimulatedPrinter) -> bytes:
    """A synthetic camera frame through the pinhole camera above: the bed (sliding along Y with
    the toolhead, as on a bed-slinger), the printed objects as solids of their current height,
    and the nozzle."""
    image = Image.new("RGB", CAMERA_SIZE, (28, 30, 34))
    draw = ImageDraw.Draw(image)
    toolhead_y = printer.position[1]

    def polygon(points: list[tuple[float, float, float]], **style) -> None:
        projected = [camera_project(x, y, z, toolhead_y) for x, y, z in points]
        if all(point is not None for point in projected):
            draw.polygon(projected, **style)

    corners = [(0.0, 0.0, 0.0), (BED_X_MM, 0.0, 0.0), (BED_X_MM, BED_Y_MM, 0.0), (0.0, BED_Y_MM, 0.0)]
    polygon(corners, fill=(64, 66, 72))
    for step in range(20, int(BED_X_MM), 20):
        for line in (((step, 0.0, 0.0), (step, BED_Y_MM, 0.0)), ((0.0, step, 0.0), (BED_X_MM, step, 0.0))):
            ends = [camera_project(x, y, z, toolhead_y) for x, y, z in line]
            if None not in ends:
                draw.line(ends, fill=(80, 82, 90))

    if printer.filename and printer.layer > 0:
        height = FIRST_LAYER_HEIGHT + (printer.layer - 1) * printer.layer_height
        for obj in printer.objects:
            color = (110, 110, 115) if obj.name in printer.excluded else (232, 128, 48)
            side = tuple(int(channel * 0.7) for channel in color)
            base = [(x, y, 0.0) for x, y in obj.polygon]
            top = [(x, y, height) for x, y in obj.polygon]
            faces = [[base[i], base[(i + 1) % 4], top[(i + 1) % 4], top[i]] for i in range(4)]
            # Painter's algorithm: farthest faces first, the top face last.
            faces.sort(key=lambda face: -sum(y for _, y, _ in face))
            for face in faces:
                polygon(face, fill=side)
            polygon(top, fill=color, outline=(255, 200, 150))

    nozzle = camera_project(printer.position[0], printer.position[1], printer.position[2] + 3.0, toolhead_y)
    if nozzle is not None:
        draw.ellipse([nozzle[0] - 6, nozzle[1] - 6, nozzle[0] + 6, nozzle[1] + 6], fill=(220, 40, 40))
    draw.text((10, 10), f"MOCK  {printer.state}  capa {printer.layer}/{printer.layer_count}", fill=(230, 230, 230))
    draw.text((10, 26), datetime.now().strftime("%H:%M:%S"), fill=(200, 200, 200))

    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", quality=80)
    return buffer.getvalue()


# --- App ------------------------------------------------------------------------------------------

printer: SimulatedPrinter
# Seconds the pause answer is held back after the state has changed: the real PAUSE macro parks the head
# (~9 s on the Creality Hi) before Moonraker answers.
pause_seconds = 0.0
# Seconds a resume takes: the real RESUME macro reheats the nozzle and travels back to the part, the state stays
# "paused" until it ends and the request is answered then (45 to 65 s on the Creality Hi).
resume_seconds = 0.0
auth_required_prefixes: tuple[str, ...] = ()
auto_start = False


class WsClient:
    def __init__(self, ws: WebSocket) -> None:
        self.ws = ws
        self.subscription: dict[str, list[str] | None] = {}
        self.last_sent: dict[str, dict] = {}

    async def send(self, payload: dict) -> None:
        await self.ws.send_text(json.dumps(payload))

    def status_diff(self, status: dict) -> dict:
        diff = {}
        for name, values in status.items():
            previous = self.last_sent.setdefault(name, {})
            changed = {key: value for key, value in values.items() if previous.get(key, object()) != value}
            if changed:
                diff[name] = changed
                previous.update(changed)
        return diff


clients: set[WsClient] = set()


async def _simulation_loop() -> None:
    while True:
        await asyncio.sleep(TICK_SECONDS)
        printer.tick(TICK_SECONDS)


async def _status_loop() -> None:
    while True:
        await asyncio.sleep(STATUS_INTERVAL_SECONDS)
        printer.new_noise_round()
        # One status round for the union of every client's subscription (None = all fields).
        wanted: dict[str, list[str] | None] = {}
        for client in clients:
            for name, fields in client.subscription.items():
                if fields is None or wanted.get(name, []) is None:
                    wanted[name] = None
                else:
                    wanted[name] = sorted({*wanted.get(name, []), *fields})
        if not wanted:
            continue
        status = printer.status(wanted)
        eventtime = printer.eventtime()
        for client in list(clients):
            own = {
                name: {key: value for key, value in status[name].items() if not fields or key in fields}
                for name, fields in client.subscription.items()
                if name in status
            }
            diff = client.status_diff(own)
            if diff:
                await _safe_send(client, {"jsonrpc": "2.0", "method": "notify_status_update", "params": [diff, eventtime]})


async def _outbox_loop() -> None:
    while True:
        message = await printer.outbox.get()
        for client in list(clients):
            await _safe_send(client, message)


async def _proc_stats_loop() -> None:
    # Moonraker pushes its process stats to every client once per second.
    while True:
        await asyncio.sleep(1.0)
        payload = {"jsonrpc": "2.0", "method": "notify_proc_stat_update", "params": [_proc_stats(compact=True)]}
        for client in list(clients):
            await _safe_send(client, payload)


async def _safe_send(client: WsClient, payload: dict) -> None:
    try:
        await client.send(payload)
    except Exception:
        clients.discard(client)


def _proc_stats(compact: bool = False) -> dict:
    now = time.time()
    sample = {"time": now, "cpu_usage": round(2.5 + random.random(), 2), "memory": 31000, "mem_units": "kB"}
    stats = {
        "moonraker_stats": sample if compact else [sample],
        "cpu_temp": round(47.0 + random.random(), 2),
        "network": {"wlan0": {"rx_bytes": int(now) % 10**8, "tx_bytes": int(now * 3) % 10**8, "bandwidth": 2500.0}},
        "system_cpu_usage": {"cpu": round(12 + random.random() * 5, 2)},
        "system_memory": {"total": 1000000, "available": 712000, "used": 288000},
        "websocket_connections": len(clients),
    }
    if not compact:
        stats["throttled_state"] = {"bits": 0, "flags": []}
        stats["system_uptime"] = round(time.monotonic() - printer.boot_monotonic + 1000.0, 2)
    return stats


@asynccontextmanager
async def lifespan(_app: FastAPI):
    tasks = [asyncio.create_task(loop()) for loop in (_simulation_loop, _status_loop, _outbox_loop, _proc_stats_loop)]
    if auto_start:
        printer.start(MOCK_FILE)
    yield
    for task in tasks:
        task.cancel()


app = FastAPI(lifespan=lifespan)


def _ok(result) -> dict:
    return {"result": result}


def _error(status_code: int, message: str) -> JSONResponse:
    return JSONResponse({"error": {"code": status_code, "message": message, "traceback": ""}}, status_code=status_code)


@app.middleware("http")
async def _auth_and_request_log(request: Request, call_next):
    if request.url.path.startswith(auth_required_prefixes):
        return _error(401, "Unauthorized")
    started = time.monotonic()
    response = await call_next(request)
    if request.method != "GET":
        client = request.client.host if request.client else "?"
        printer.log_moonraker(
            f"[app.py:log_request()] - {response.status_code} {request.method} {request.url.path} "
            f"({client}) [_TRUSTED_USER_] {(time.monotonic() - started) * 1000:.2f}ms"
        )
    return response


def _printer_info() -> dict:
    return {
        "state": "ready",
        "state_message": "Printer is ready",
        "hostname": "mock-hi",
        "klipper_path": "/home/mock/klipper",
        "python_path": "/home/mock/klippy-env/bin/python",
        "log_file": "/home/mock/printer_data/logs/klippy.log",
        "config_file": "/home/mock/printer_data/config/printer.cfg",
        "software_version": "v0.12.0-mock",
        "cpu_info": "mock cpu",
    }


def _server_info() -> dict:
    return {
        "klippy_connected": True,
        "klippy_state": "ready",
        "components": ["klippy_apis", "file_manager", "history", "webcam", "machine", "proc_stats"],
        "failed_components": [],
        "registered_directories": ["config", "logs", "gcodes"],
        "warnings": [],
        "websocket_count": len(clients),
        "moonraker_version": "v0.9.3-mock",
        "api_version": [1, 5, 0],
        "api_version_string": "1.5.0",
    }


def _parse_objects_query(request: Request) -> dict[str, list[str] | None]:
    return {
        name: [field for field in value.split(",") if field] or None for name, value in request.query_params.multi_items()
    }


@app.get("/printer/info")
async def printer_info() -> dict:
    return _ok(_printer_info())


@app.get("/server/info")
async def server_info() -> dict:
    return _ok(_server_info())


@app.get("/printer/objects/list")
async def objects_list() -> dict:
    return _ok({"objects": printer.object_names()})


@app.get("/printer/objects/query")
async def objects_query(request: Request) -> dict:
    return _ok({"eventtime": printer.eventtime(), "status": printer.status(_parse_objects_query(request))})


async def _print_action(action) -> JSONResponse | dict:
    try:
        action()
    except GcodeError as error:
        return _error(400, str(error))
    return _ok("ok")


@app.post("/printer/print/start")
async def print_start(filename: str = MOCK_FILE):
    return await _print_action(lambda: printer.start(filename))


@app.post("/printer/print/pause")
async def print_pause():
    result = await _print_action(printer.pause)
    if pause_seconds:
        await asyncio.sleep(pause_seconds)
    return result


@app.post("/printer/print/resume")
async def print_resume():
    if resume_seconds and printer.state == "paused":
        await asyncio.sleep(resume_seconds)
    return await _print_action(printer.resume)


@app.post("/printer/print/cancel")
async def print_cancel():
    return await _print_action(printer.cancel)


@app.post("/printer/gcode/script")
async def gcode_script(request: Request, script: str | None = None):
    if script is None:
        try:
            script = (await request.json()).get("script")
        except ValueError:
            script = None
    if not script:
        return _error(400, "No script given")
    return await _print_action(lambda: printer.run_gcode(script))


@app.post("/mock/error")
async def mock_error(x: float = 292.424, y: float = 249.610, z: float = 28.401):
    return await _print_action(lambda: printer.fail(x, y, z))


@app.post("/mock/filament")
async def mock_filament(detected: bool = False) -> dict:
    printer.filament_detected = detected
    return _ok("ok")


@app.post("/mock/heater")
async def mock_heater(
    heater: str = "extruder", hold_power: float | None = None, tau: float | None = None, temperature: float | None = None
) -> dict:
    """Simulation controls for one heater: the power it needs to hold its target (raise it to
    simulate wear), its time constant (raise it to heat more slowly) and its current temperature
    (set it to room temperature to simulate the time between prints)."""
    target = printer.bed if heater == "bed" else printer.extruder
    if hold_power is not None:
        target.hold_power = hold_power
    if tau is not None:
        target.tau = tau
    if temperature is not None:
        target.temperature = temperature
    return _ok({"hold_power": target.hold_power, "tau": target.tau, "temperature": round(target.temperature, 2)})


@app.post("/mock/screen")
async def mock_screen(script: str):
    """A change made on the printer's touchscreen: it takes effect but leaves no console trace."""
    return await _print_action(lambda: printer.run_from_screen(script))


@app.get("/server/gcode_store")
async def gcode_store(count: int = 100) -> dict:
    return _ok({"gcode_store": list(printer.gcode_store)[-count:]})


@app.get("/server/history/list")
async def history_list(limit: int = 50, start: int = 0, order: str = "desc") -> dict:
    jobs = list(reversed(printer.history)) if order == "desc" else list(printer.history)
    return _ok({"count": len(jobs), "jobs": jobs[start : start + limit]})


@app.get("/server/history/totals")
async def history_totals() -> dict:
    finished = [job for job in printer.history if job["status"] != "in_progress"]
    return _ok(
        {
            "job_totals": {
                "total_jobs": len(finished),
                "total_time": round(sum(job["total_duration"] for job in finished), 2),
                "total_print_time": round(sum(job["print_duration"] for job in finished), 2),
                "total_filament_used": round(sum(job["filament_used"] for job in finished), 2),
                "longest_job": max((job["total_duration"] for job in finished), default=0.0),
                "longest_print": max((job["print_duration"] for job in finished), default=0.0),
            }
        }
    )


def _log_files() -> dict[str, bytes]:
    return {
        "klippy.log": ("\n".join(printer.klippy_log) + "\n").encode(),
        "moonraker.log": ("\n".join(printer.moonraker_log) + "\n").encode(),
    }


@app.get("/server/files/list")
async def files_list(root: str = "gcodes"):
    if root == "gcodes":
        metadata = printer.file_metadata(MOCK_FILE)
        return _ok([{"path": MOCK_FILE, "modified": metadata["modified"], "size": metadata["size"], "permissions": "rw"}])
    if root == "logs":
        now = time.time()
        return _ok([{"path": name, "modified": now, "size": len(data), "permissions": "r"} for name, data in _log_files().items()])
    return _error(400, f"Invalid root: {root}")


@app.get("/server/files/metadata")
async def files_metadata(filename: str):
    metadata = printer.file_metadata(filename)
    if metadata is None:
        return _error(404, f"Metadata not available for <{filename}>")
    return _ok(metadata)


def _ranged(data: bytes, range_header: str | None, media_type: str) -> Response:
    """Enough of HTTP ranges for the discovery script: 'bytes=a-b', 'bytes=a-' and 'bytes=-n'."""
    match = re.fullmatch(r"bytes=(\d*)-(\d*)", range_header or "")
    if not match or not (match.group(1) or match.group(2)):
        return Response(data, media_type=media_type, headers={"Accept-Ranges": "bytes"})
    total = len(data)
    if match.group(1):
        start = int(match.group(1))
        end = min(int(match.group(2)), total - 1) if match.group(2) else total - 1
    else:
        start = max(0, total - int(match.group(2)))
        end = total - 1
    if start >= total or start > end:
        return Response(status_code=416, headers={"Content-Range": f"bytes */{total}"})
    return Response(
        data[start : end + 1],
        status_code=206,
        media_type=media_type,
        headers={"Content-Range": f"bytes {start}-{end}/{total}", "Accept-Ranges": "bytes"},
    )


@app.get("/server/files/gcodes/{path:path}")
async def gcode_file(path: str, request: Request):
    if path != MOCK_FILE:
        return _error(404, f"File does not exist: {path}")
    return _ranged(printer.gcode_bytes(), request.headers.get("range"), "text/plain")


@app.get("/server/files/logs/{path:path}")
async def log_file(path: str, request: Request):
    data = _log_files().get(path)
    if data is None:
        return _error(404, f"File does not exist: {path}")
    return _ranged(data, request.headers.get("range"), "text/plain")


@app.get("/server/webcams/list")
async def webcams_list() -> dict:
    return _ok(
        {
            "webcams": [
                {
                    "name": "Mock Hi Cam",
                    "location": "printer",
                    "service": "mjpegstreamer-adaptive",
                    "enabled": True,
                    "icon": "mdiWebcam",
                    "target_fps": 10,
                    "target_fps_idle": 2,
                    "stream_url": "/webcam/?action=stream",
                    "snapshot_url": "/webcam/?action=snapshot",
                    "flip_horizontal": False,
                    "flip_vertical": False,
                    "rotation": 0,
                    "aspect_ratio": "4:3",
                    "extra_data": {},
                    "source": "config",
                    "uid": "00000000-0000-4000-8000-000000000001",
                }
            ]
        }
    )


@app.get("/webcam/")
async def webcam(action: str = "snapshot"):
    if action != "stream":
        return Response(render_camera(printer), media_type="image/jpeg")

    async def frames():
        while True:
            jpeg = render_camera(printer)
            yield (
                b"--boundarydonotcross\r\nContent-Type: image/jpeg\r\nContent-Length: "
                + str(len(jpeg)).encode()
                + b"\r\n\r\n"
                + jpeg
                + b"\r\n"
            )
            await asyncio.sleep(0.2)

    return StreamingResponse(frames(), media_type="multipart/x-mixed-replace; boundary=boundarydonotcross")


@app.get("/machine/system_info")
async def system_info() -> dict:
    return _ok(
        {
            "system_info": {
                "cpu_info": {"cpu_count": 4, "bits": "64bit", "processor": "aarch64", "cpu_desc": "mock",
                             "serial_number": "MOCK-SERIAL", "hardware_desc": "mock", "model": "Mock Hi",
                             "total_memory": 1000000, "memory_units": "kB"},
                "sd_info": {},
                "distribution": {"name": "Mock Linux", "id": "mock", "version": "1"},
                "available_services": ["klipper", "moonraker"],
                "service_state": {"klipper": {"active_state": "active", "sub_state": "running"},
                                  "moonraker": {"active_state": "active", "sub_state": "running"}},
                "virtualization": {"virt_type": "none", "virt_identifier": "none"},
                "network": {"wlan0": {"mac_address": "00:00:00:00:00:00",
                                      "ip_addresses": [{"family": "ipv4", "address": "127.0.0.1", "is_link_local": False}]}},
                "canbus": {},
            }
        }
    )


@app.get("/machine/proc_stats")
async def proc_stats() -> dict:
    return _ok(_proc_stats())


async def _rpc(client: WsClient, method: str, params: dict):
    if method == "server.info":
        return _server_info()
    if method == "printer.info":
        return _printer_info()
    if method == "server.connection.identify":
        return {"connection_id": id(client)}
    if method == "printer.objects.list":
        return {"objects": printer.object_names()}
    if method == "printer.objects.query":
        return {"eventtime": printer.eventtime(), "status": printer.status(params.get("objects") or {})}
    if method == "printer.objects.subscribe":
        client.subscription = {name: (fields or None) for name, fields in (params.get("objects") or {}).items()}
        client.last_sent = {}
        status = printer.status(client.subscription)
        client.status_diff(status)
        return {"eventtime": printer.eventtime(), "status": status}
    if method == "server.gcode_store":
        return {"gcode_store": list(printer.gcode_store)[-int(params.get("count", 100)) :]}
    actions = {
        "printer.print.pause": printer.pause,
        "printer.print.resume": printer.resume,
        "printer.print.cancel": printer.cancel,
        "printer.print.start": lambda: printer.start(params.get("filename", MOCK_FILE)),
        "printer.gcode.script": lambda: printer.run_gcode(params.get("script", "")),
    }
    if method in actions:
        try:
            actions[method]()
        except GcodeError as error:
            raise RpcError(400, str(error)) from None
        return "ok"
    raise RpcError(-32601, "Method not found")


class RpcError(Exception):
    def __init__(self, code: int, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@app.websocket("/websocket")
async def websocket_endpoint(ws: WebSocket) -> None:
    if "/websocket".startswith(auth_required_prefixes):
        await ws.close(code=1008)  # rejected before accept: the client sees HTTP 403
        return
    await ws.accept()
    client = WsClient(ws)
    clients.add(client)
    try:
        while True:
            raw = await ws.receive_text()
            try:
                message = json.loads(raw)
            except json.JSONDecodeError:
                continue
            request_id = message.get("id")
            try:
                reply = {"jsonrpc": "2.0", "result": await _rpc(client, message.get("method", ""), message.get("params") or {}), "id": request_id}
            except RpcError as error:
                reply = {"jsonrpc": "2.0", "error": {"code": error.code, "message": error.message}, "id": request_id}
            await client.send(reply)
    except WebSocketDisconnect:
        pass
    finally:
        clients.discard(client)


def main() -> None:
    global printer, auth_required_prefixes, auto_start, camera_on_bed, pause_seconds, resume_seconds

    parser = argparse.ArgumentParser(description="Impresora Klipper/Moonraker simulada para pruebas.")
    parser.add_argument("--host", default="127.0.0.1", help="0.0.0.0 para aceptar conexiones de otros equipos/contenedores")
    parser.add_argument("--port", type=int, default=7125)
    parser.add_argument("--layers", type=int, default=40, help="capas de la impresion simulada")
    parser.add_argument("--layer-seconds", type=float, default=8.0, help="segundos por capa al 100%% de velocidad")
    parser.add_argument("--layer-height", type=float, default=0.2)
    parser.add_argument("--auto-start", action="store_true", help=f"empezar a imprimir {MOCK_FILE} al arrancar")
    parser.add_argument("--require-auth", action="append", default=[], help="prefijo de ruta que responde 401 (repetible)")
    parser.add_argument("--fast-heat", action="store_true", help="calentar casi al instante")
    parser.add_argument(
        "--camera-on-bed", action="store_true", help="la camara se mueve con la cama (por defecto esta fija al marco)"
    )
    parser.add_argument(
        "--pause-seconds", type=float, default=0.0,
        help="segundos que tarda en responder la pausa, con el estado ya cambiado (la real: ~9 s)",
    )
    parser.add_argument(
        "--resume-seconds", type=float, default=0.0,
        help="segundos que tarda la reanudacion: el estado sigue en paused hasta el final (la real: 45 a 65 s)",
    )
    parser.add_argument("--seed", type=int, default=7)
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)
    auth_required_prefixes = tuple(args.require_auth)
    auto_start = args.auto_start
    camera_on_bed = args.camera_on_bed
    pause_seconds = args.pause_seconds
    resume_seconds = args.resume_seconds
    printer = SimulatedPrinter(
        args.layers, args.layer_seconds, args.layer_height, args.seed, heater_tau_scale=0.05 if args.fast_heat else 1.0
    )
    uvicorn.run(app, host=args.host, port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
