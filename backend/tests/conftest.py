import asyncio
import importlib.util
import os
import socket
import sys
import threading
import time
from pathlib import Path

import pytest
import uvicorn
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
_TABLES = (
    "printer_events, telemetry_samples, alerts, detections, layer_captures, layers, print_jobs, cameras, printers, "
    "app_settings"
)


def load_script(name: str):
    """backend/scripts is not a package; load a script as a module from its path."""
    module_name = f"scripts_{name}"
    if module_name not in sys.modules:
        spec = importlib.util.spec_from_file_location(module_name, SCRIPTS_DIR / f"{name}.py")
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)
    return sys.modules[module_name]


@pytest.fixture
def discovery():
    return load_script("moonraker_discovery")


@pytest.fixture
def mock_moonraker():
    """The simulated printer's app with a fresh printer (near-instant heating), ready to be
    served in-process."""
    mock = load_script("mock_moonraker")
    mock.printer = mock.SimulatedPrinter(layers=4, layer_seconds=2.0, layer_height=0.2, seed=1, heater_tau_scale=0.05)
    mock.auth_required_prefixes = ()
    mock.auto_start = False
    mock.pause_seconds = 0.0
    mock.resume_seconds = 0.0
    return mock


@pytest.fixture
def mock_server(mock_moonraker):
    """The simulated printer served over HTTP and WebSocket on a free local port, in a
    background thread. Drive it through HTTP, not by touching mock_moonraker.printer: the
    simulation runs in the server's own event loop."""
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(mock_moonraker.app, host="127.0.0.1", port=port, log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 10
    while not server.started:
        if time.monotonic() > deadline:
            raise RuntimeError("the simulated printer did not start")
        time.sleep(0.05)
    yield f"http://127.0.0.1:{port}"
    server.should_exit = True
    thread.join(timeout=10)


@pytest.fixture
def db_url():
    """Postgres for integration tests, from TEST_DATABASE_URL. Only a database whose name ends in
    _test is accepted: the tests empty its tables."""
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.skip("TEST_DATABASE_URL no definida: se omiten las pruebas contra Postgres")
    if not url.rstrip("/").endswith("_test"):
        pytest.fail("TEST_DATABASE_URL debe apuntar a una base cuyo nombre termine en _test")
    return url


@pytest.fixture
def with_db(db_url):
    """with_db(scenario) runs `await scenario(session_factory)` on emptied tables and returns its
    result. The engine lives inside the event loop asyncio.run creates, since asyncpg
    connections are bound to their loop."""

    def run(scenario):
        async def main():
            engine = create_async_engine(db_url)
            try:
                async with engine.begin() as connection:
                    await connection.execute(text(f"TRUNCATE {_TABLES} RESTART IDENTITY CASCADE"))
                return await scenario(async_sessionmaker(engine, expire_on_commit=False))
            finally:
                await engine.dispose()

        return asyncio.run(main())

    return run
