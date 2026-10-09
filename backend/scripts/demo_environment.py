"""Demo mode: the whole system running against the simulated printer, without the real one.

Starts on this machine, isolated from the real system:
  - its own database, printwatch_demo (created and migrated here; the real one is never touched),
  - a second backend on port 8010, on Redis database 2 and with its channels prefixed "demo:",
  - the simulated printer (scripts/mock_moonraker.py) on port 7140,
  - a demo capture loop: on each layer it saves the simulated camera's frame and stores a
    detection. There is no model here: the detections are SYNTHETIC (raw_output.synthetic = true),
    placed on purpose at known points of the parts, so the bed map, the jam alert and the spaghetti
    auto-pause (which pauses the SIMULATED printer) can be seen working.
Then it plays a scenario: a print with interventions from the console and from the "screen" that
ends normally, a cancelled one, and one that triggers the auto-pause, is resumed from the console
and keeps printing.

Usage, from the repo root, with Postgres and Redis up:
    backend\\.venv\\Scripts\\python.exe backend\\scripts\\demo_environment.py
and the web against the demo backend, in another terminal:
    $env:VITE_API_BASE_URL="http://localhost:8010"; cd frontend; npm run dev -- --port 5181
User demo / demo-printwatch. Ctrl+C stops everything; the demo database stays (--reset starts over).
"""

import argparse
import asyncio
import base64
import importlib.util
import json
import os
import subprocess
import sys
import time
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))

import httpx  # noqa: E402
import redis.asyncio as redis  # noqa: E402
from sqlalchemy import select, text  # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402

from app.core.config import settings  # noqa: E402
from app.core.security import hash_password  # noqa: E402
from app.db.models import Detection, Layer, LayerCapture, ModelVersion, User, UserRole  # noqa: E402

DEMO_DB = "printwatch_demo"
API_PORT = 8010
MOCK_PORT = 7140
REDIS_DB = 2
PREFIX = "demo:"
USERNAME, PASSWORD = "demo", "demo-printwatch"
STORAGE = ROOT / "storage" / "demo_snapshots"
API = f"http://127.0.0.1:{API_PORT}/api/v1"
MOCK = f"http://127.0.0.1:{MOCK_PORT}"
WIDTH, HEIGHT = 640, 480
BOX_HALF = (26 / WIDTH, 20 / HEIGHT)


def load_mock_module():
    spec = importlib.util.spec_from_file_location("demo_mock_moonraker", BACKEND / "scripts" / "mock_moonraker.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


MOCK_MODULE = load_mock_module()  # for its camera model: where a bed point lands in the image


def demo_database_url() -> str:
    return settings.database_url.rsplit("/", 1)[0] + f"/{DEMO_DB}"


async def ensure_database(reset: bool) -> None:
    server = create_async_engine(settings.database_url.rsplit("/", 1)[0] + "/postgres", isolation_level="AUTOCOMMIT")
    async with server.connect() as connection:
        exists = await connection.scalar(text("SELECT 1 FROM pg_database WHERE datname = :name"), {"name": DEMO_DB})
        if exists and reset:
            await connection.execute(text(f'DROP DATABASE "{DEMO_DB}"'))
            exists = False
        if not exists:
            await connection.execute(text(f'CREATE DATABASE "{DEMO_DB}"'))
            print(f"Base de datos {DEMO_DB} creada.", flush=True)
    await server.dispose()


def child_env() -> dict:
    return {
        **os.environ,
        "DATABASE_URL": demo_database_url(),
        "REDIS_URL": f"{settings.redis_url.rsplit('/', 1)[0]}/{REDIS_DB}",
        "REDIS_CHANNEL_PREFIX": PREFIX,
        "STORAGE_ROOT": str(STORAGE),
    }


def start_processes(layers: int, layer_seconds: float) -> list[subprocess.Popen]:
    subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], cwd=BACKEND, env=child_env(), check=True)
    STORAGE.mkdir(parents=True, exist_ok=True)
    # Heaters at the simulation's normal speed (seconds, not instant), so the printer-health page
    # can measure heat-ups.
    mock = subprocess.Popen(
        [sys.executable, "scripts/mock_moonraker.py", "--port", str(MOCK_PORT), "--layers", str(layers),
         "--layer-seconds", str(layer_seconds)],
        cwd=BACKEND,
    )
    backend = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(API_PORT), "--log-level", "warning"],
        cwd=BACKEND,
        env=child_env(),
    )
    return [mock, backend]


async def wait_for(url: str, seconds: float = 60) -> None:
    deadline = time.monotonic() + seconds
    async with httpx.AsyncClient(timeout=3) as client:
        while True:
            try:
                if (await client.get(url)).status_code < 500:
                    return
            except httpx.HTTPError:
                pass
            if time.monotonic() > deadline:
                raise RuntimeError(f"{url} did not come up")
            await asyncio.sleep(0.5)


async def seed(session_factory) -> tuple[httpx.AsyncClient, int, int, int]:
    """Demo user, printer, camera, calibration and the synthetic model version (idempotent)."""
    async with session_factory() as db:
        if await db.scalar(select(User).where(User.username == USERNAME)) is None:
            db.add(User(username=USERNAME, email="demo@printwatch.local", hashed_password=hash_password(PASSWORD), role=UserRole.admin))
        model = await db.scalar(select(ModelVersion).where(ModelVersion.name == "demo-sintetico"))
        if model is None:
            model = ModelVersion(
                name="demo-sintetico",
                file_path="(sin modelo: detecciones sintéticas del modo demostración)",
                classes=["spaghetti", "warping", "stringing", "layer_shift", "under_extrusion", "blob_over_extrusion"],
            )
            db.add(model)
        await db.commit()
        model_id = model.id

    api = httpx.AsyncClient(base_url=API, timeout=15)
    token = (await api.post("/auth/login", data={"username": USERNAME, "password": PASSWORD})).json()["access_token"]
    api.headers["Authorization"] = f"Bearer {token}"

    printers = (await api.get("/printers")).json()
    printer = next((item for item in printers if item["octoprint_url"] == MOCK), None)
    if printer is None:
        printer = (
            await api.post(
                "/printers",
                json={"name": "Creality Hi (simulada)", "model": "Impresora simulada", "octoprint_url": MOCK, "integration_type": "moonraker"},
            )
        ).json()
    cameras = (await api.get(f"/printers/{printer['id']}/cameras")).json()
    camera = cameras[0] if cameras else (
        await api.post(
            f"/printers/{printer['id']}/cameras",
            json={"name": "Cámara simulada", "source_type": "mjpeg_http", "source_uri": f"{MOCK}/webcam/?action=stream"},
        )
    ).json()

    if (await api.get(f"/cameras/{camera['id']}/calibration")).status_code == 404:
        # The corners as marked on a frame taken with the head at the camera model's reference Y.
        reference_y = MOCK_MODULE.NOZZLE_WORLD_Y
        corners = [MOCK_MODULE.camera_project(x, y, 0.0, reference_y) for x, y in ((0, 0), (260, 0), (260, 260), (0, 260))]
        response = await api.post(
            f"/cameras/{camera['id']}/calibration",
            json={
                "image_points": [[u / WIDTH, v / HEIGHT] for u, v in corners],
                "image_width": WIDTH,
                "image_height": HEIGHT,
                "bed_moves_in_image": True,
                "reference_y": reference_y,
            },
        )
        response.raise_for_status()
    return api, printer["id"], camera["id"], model_id


class DemoCapture:
    """Stands in for the capture process and the model: a frame per layer from the simulated
    camera, and the synthetic defects of the current scenario step."""

    def __init__(self, session_factory, redis_client, printer_id: int, camera_id: int, model_id: int) -> None:
        self.session_factory = session_factory
        self.redis = redis_client
        self.printer_id = printer_id
        self.camera_id = camera_id
        self.model_id = model_id
        self.plan: dict[int, list[tuple[str, float, float, float]]] = {}  # layer -> (class, x, y, confidence)
        self.http = httpx.AsyncClient(timeout=10)

    async def keep_frames(self) -> None:
        """The live video: the simulated camera's frame a few times a second."""
        while True:
            try:
                frame = (await self.http.get(f"{MOCK}/webcam/?action=snapshot")).content
                await self.redis.mset(
                    {
                        f"latest_frame:{self.camera_id}": base64.b64encode(frame).decode("ascii"),
                        f"latest_frame_at:{self.camera_id}": str(time.time()),
                    }
                )
            except httpx.HTTPError:
                pass
            await asyncio.sleep(0.4)

    async def listen(self) -> None:
        pubsub = self.redis.pubsub()
        await pubsub.subscribe(f"{PREFIX}layer_ready:{self.printer_id}")
        async for message in pubsub.listen():
            if message["type"] == "message":
                try:
                    await self.capture(json.loads(message["data"]))
                except Exception as error:  # a demo frame that fails must not stop the demo
                    print(f"  (captura de demo falló: {error})", flush=True)

    async def capture(self, payload: dict) -> None:
        job_id, number = payload["job_id"], payload["layer_number"]
        z = float(payload["z_height"])
        frame = (await self.http.get(f"{MOCK}/webcam/?action=snapshot")).content
        status = (await self.http.get(f"{MOCK}/printer/objects/query", params={"motion_report": "live_position"})).json()
        head_y = status["result"]["status"]["motion_report"]["live_position"][1]

        relative = f"{self.printer_id}/{job_id}/layer_{number}_primary.jpg"
        (STORAGE / relative).parent.mkdir(parents=True, exist_ok=True)
        (STORAGE / relative).write_bytes(frame)

        boxes = []
        for class_name, x, y, confidence in self.plan.get(number, []):
            u, v = MOCK_MODULE.camera_project(x, y, z, head_y)
            u, v = u / WIDTH, v / HEIGHT
            boxes.append({"class": class_name, "confidence": confidence, "box": [u - BOX_HALF[0], v - BOX_HALF[1], u + BOX_HALF[0], v + BOX_HALF[1]]})
        classes = sorted({box["class"] for box in boxes})

        async with self.session_factory() as db:
            layer_id = await db.scalar(select(Layer.id).where(Layer.job_id == job_id, Layer.layer_number == number))
            if layer_id is None:
                return
            capture = LayerCapture(layer_id=layer_id, camera_id=self.camera_id, image_path=relative)
            db.add(capture)
            await db.flush()
            detection = Detection(
                capture_id=capture.id,
                model_version_id=self.model_id,
                has_defect=bool(boxes),
                max_confidence=Decimal(str(max((box["confidence"] for box in boxes), default=0))) if boxes else None,
                defect_classes=classes,
                raw_output={
                    "detections": boxes,
                    "frame": {"width": WIDTH, "height": HEIGHT, "roi": {"x": 0, "y": 0, "w": WIDTH, "h": HEIGHT}},
                    "synthetic": True,
                },
            )
            db.add(detection)
            await db.commit()

        common = {"printer_id": self.printer_id, "job_id": job_id, "layer_number": number, "camera_id": self.camera_id}
        await self.redis.publish(f"{PREFIX}events:layer_captured", json.dumps({**common, "capture_id": capture.id, "layer_id": layer_id, "image_path": relative}))
        await self.redis.publish(
            f"{PREFIX}events:detection_result",
            json.dumps({**common, "detection_id": detection.id, "capture_id": capture.id, "has_defect": bool(boxes),
                        "max_confidence": float(detection.max_confidence) if detection.max_confidence else None, "defect_classes": classes}),
        )
        await self.redis.publish(
            f"{PREFIX}events:detection_boxes",
            json.dumps({**common, "detection_id": detection.id, "capture_id": capture.id,
                        "boxes": [{"class": box["class"], "confidence": box["confidence"], "x1": box["box"][0], "y1": box["box"][1],
                                   "x2": box["box"][2], "y2": box["box"][3]} for box in boxes]}),
        )


async def mock_state() -> tuple[str, int]:
    async with httpx.AsyncClient(timeout=5) as client:
        status = (await client.get(f"{MOCK}/printer/objects/query", params={"print_stats": "state", "virtual_sdcard": "layer"})).json()
    status = status["result"]["status"]
    return status["print_stats"]["state"], status["virtual_sdcard"]["layer"]


async def until(condition, seconds: float = 900) -> None:
    deadline = time.monotonic() + seconds
    while not await condition():
        if time.monotonic() > deadline:
            raise RuntimeError("the demo scenario timed out")
        await asyncio.sleep(0.5)


async def at_layer(number: int) -> None:
    async def reached():
        state, layer = await mock_state()
        return state != "printing" or layer >= number

    await until(reached)


async def in_state(*states: str) -> None:
    async def reached():
        return (await mock_state())[0] in states

    await until(reached)


async def mock_post(path: str, **params) -> None:
    async with httpx.AsyncClient(timeout=10) as client:
        (await client.post(MOCK + path, params=params)).raise_for_status()


async def scenario(capture: DemoCapture) -> None:
    print("1/3 Impresión con intervenciones (consola, pantalla, objeto excluido) que termina bien", flush=True)
    # Each defect comes after a change that explains it, so the combined score (model + telemetry)
    # has something to show: the nozzle raised before the stringing, the bed lowered from the
    # screen before the warping and the flow lowered before the under-extrusion.
    capture.plan = {
        12: [("stringing", 95.0, 150.0, 0.62)],
        13: [("stringing", 97.0, 148.0, 0.55)],
        20: [("warping", 72.0, 108.0, 0.71)],
        21: [("warping", 72.0, 107.0, 0.66)],
        26: [("under_extrusion", 100.0, 125.0, 0.58)],
        27: [("under_extrusion", 102.0, 126.0, 0.61)],
        28: [("under_extrusion", 99.0, 124.0, 0.64)],
    }
    await mock_post("/printer/print/start", filename="mock_box.gcode")
    await at_layer(6)
    await mock_post("/printer/gcode/script", script="M220 S90")
    await at_layer(10)
    await mock_post("/printer/gcode/script", script="M104 S250")
    await at_layer(14)
    await mock_post("/printer/gcode/script", script="M104 S235")
    await at_layer(16)
    await mock_post("/printer/gcode/script", script="SET_GCODE_OFFSET Z_ADJUST=0.02")
    await at_layer(17)
    await mock_post("/mock/screen", script="M140 S60")
    await at_layer(22)
    await mock_post("/printer/gcode/script", script="EXCLUDE_OBJECT NAME=BOX_2")
    await at_layer(24)
    await mock_post("/printer/gcode/script", script="M221 S90")
    await at_layer(30)
    await mock_post("/printer/gcode/script", script="M221 S100")
    await in_state("complete")

    print("2/3 Impresión cancelada desde la consola", flush=True)
    capture.plan = {3: [("blob_over_extrusion", 165.0, 130.0, 0.31)]}
    await mock_post("/printer/print/start", filename="mock_box.gcode")
    await at_layer(5)
    await mock_post("/printer/gcode/script", script="CANCEL_PRINT")
    await in_state("cancelled")

    print("3/3 Spaghetti en tres capas seguidas: la pausa automática pausa la impresora SIMULADA", flush=True)
    capture.plan = {
        8: [("spaghetti", 165.0, 132.0, 0.74)],
        9: [("spaghetti", 168.0, 130.0, 0.81)],
        10: [("spaghetti", 166.0, 128.0, 0.79)],
        14: [("stringing", 92.0, 152.0, 0.48)],
    }
    await mock_post("/printer/print/start", filename="mock_box.gcode")
    await in_state("paused")
    await asyncio.sleep(6)
    await mock_post("/printer/gcode/script", script="RESUME")
    print("Listo: la tercera impresión sigue en curso para ver la pantalla en vivo.", flush=True)


async def health_prints(capture: DemoCapture, count: int = 8) -> None:
    """Short prints for the printer-health page: the first ones set its baseline; in the last two
    the nozzle heater needs more power to hold its target and the bed heats more slowly."""
    print(f"Salud: {count} impresiones cortas; en las 2 últimas, desgaste simulado de los calentadores", flush=True)
    capture.plan = {}
    for number in range(1, count + 1):
        worn = number > count - 2
        hold_power = 0.30 if not worn else 0.36 if number < count else 0.40
        # Between real prints the heaters cool down to room temperature; the simulation is told so.
        await mock_post("/mock/heater", heater="extruder", temperature=25, tau=3.0, hold_power=hold_power)
        await mock_post("/mock/heater", heater="bed", temperature=25, tau=9.0 if worn else 6.0)
        await mock_post("/printer/print/start", filename="mock_box.gcode")
        await in_state("complete")
        print(f"  impresión {number}/{count} terminada", flush=True)
    await mock_post("/mock/heater", heater="extruder", hold_power=0.30)
    await mock_post("/mock/heater", heater="bed", tau=6.0)


async def incident_print(capture: DemoCapture) -> None:
    """Spaghetti in three layers in a row and nothing else: with AUTO_PAUSE_MODE=on the simulated printer ends up
    paused (and stays so), with warn it keeps printing; either way an incident is open to look at."""
    print("Un incidente: spaghetti en tres capas seguidas (el modo de la pausa automática es el del entorno)", flush=True)
    capture.plan = {
        8: [("spaghetti", 165.0, 132.0, 0.74)],
        9: [("spaghetti", 168.0, 130.0, 0.81), ("stringing", 92.0, 152.0, 0.43)],
        10: [("spaghetti", 166.0, 128.0, 0.92)],
    }
    await mock_post("/printer/print/start", filename="mock_box.gcode")


async def live_print(capture: DemoCapture) -> None:
    print("Una impresión en curso con algunos defectos sintéticos, sin pausa", flush=True)
    capture.plan = {
        5: [("stringing", 95.0, 150.0, 0.57)],
        6: [("stringing", 96.0, 149.0, 0.61)],
        14: [("warping", 72.0, 108.0, 0.52)],
    }
    await mock_post("/printer/print/start", filename="mock_box.gcode")


async def main() -> None:
    parser = argparse.ArgumentParser(description="Modo demostración de PrintWatch con la impresora simulada.")
    parser.add_argument("--reset", action="store_true", help="borrar la base de demostración y empezar de cero")
    parser.add_argument("--layers", type=int, default=60)
    parser.add_argument("--layer-seconds", type=float, default=3.0)
    parser.add_argument("--no-scenario", action="store_true", help="solo levantar todo, sin imprimir")
    parser.add_argument("--live", action="store_true", help="en vez del escenario completo, una sola impresión en curso")
    parser.add_argument("--incident", action="store_true", help="en vez del escenario completo, una impresión con spaghetti en tres capas seguidas (un incidente)")
    parser.add_argument(
        "--auto-pause-mode", choices=["on", "warn", "off"], default=None,
        help="AUTO_PAUSE_MODE del backend de la demostración (por defecto el del entorno)",
    )
    parser.add_argument(
        "--health", action="store_true",
        help="en vez del escenario, 8 impresiones cortas con desgaste simulado al final (usar con --layers 30 --layer-seconds 2)",
    )
    args = parser.parse_args()

    if args.auto_pause_mode:
        os.environ["AUTO_PAUSE_MODE"] = args.auto_pause_mode  # the backend child inherits it (see child_env)
    await ensure_database(args.reset)
    processes = start_processes(args.layers, args.layer_seconds)
    engine = create_async_engine(demo_database_url())
    redis_client = redis.from_url(f"{settings.redis_url.rsplit('/', 1)[0]}/{REDIS_DB}", decode_responses=True)
    tasks: list[asyncio.Task] = []
    try:
        await wait_for(f"http://127.0.0.1:{API_PORT}/health")
        await wait_for(f"{MOCK}/printer/info")
        session_factory = async_sessionmaker(engine, expire_on_commit=False)
        api, printer_id, camera_id, model_id = await seed(session_factory)
        await api.aclose()
        capture = DemoCapture(session_factory, redis_client, printer_id, camera_id, model_id)
        tasks = [asyncio.create_task(capture.keep_frames()), asyncio.create_task(capture.listen())]
        print(f"Modo demostración listo: backend en http://localhost:{API_PORT} (usuario {USERNAME} / {PASSWORD}).", flush=True)
        if not args.no_scenario:
            await asyncio.sleep(3)  # let the listener connect
            await (
                incident_print(capture) if args.incident else live_print(capture) if args.live
                else health_prints(capture) if args.health else scenario(capture)
            )
        await asyncio.Event().wait()  # keep everything up until Ctrl+C
    finally:
        for task in tasks:
            task.cancel()
        for process in processes:
            process.terminate()
        await redis_client.aclose()
        await engine.dispose()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nModo demostración detenido.", flush=True)
