import asyncio

from sqlalchemy import select

from app.db.models import IntegrationType, Printer
from app.integrations.moonraker.listener import run_moonraker_listener
from app.integrations.octoprint.listener import run_printer_listener

_LISTENERS = {
    IntegrationType.octoprint: run_printer_listener,
    IntegrationType.moonraker: run_moonraker_listener,
}


class PrinterListenerManager:
    """Owns one background reconnect-loop task per printer, picking the listener that matches
    the printer's integration_type. Printers created after startup are picked up via .start()
    (wired into the create_printer endpoint) rather than a restart; deleting/updating a printer
    does not yet stop/restart its task (known gap)."""

    def __init__(self, db_session_factory, redis_client) -> None:
        self._db_session_factory = db_session_factory
        self._redis_client = redis_client
        self._tasks: dict[int, asyncio.Task] = {}

    def _start(self, printer_id: int, integration_type: IntegrationType) -> None:
        existing = self._tasks.get(printer_id)
        if existing is not None and not existing.done():
            return
        listener = _LISTENERS[integration_type]
        self._tasks[printer_id] = asyncio.create_task(
            listener(printer_id, self._db_session_factory, self._redis_client)
        )

    async def start(self, printer_id: int) -> None:
        async with self._db_session_factory() as db:
            printer = await db.get(Printer, printer_id)
            if printer is None:
                return
            integration_type = printer.integration_type
        self._start(printer_id, integration_type)

    async def start_all_existing(self) -> None:
        async with self._db_session_factory() as db:
            result = await db.execute(select(Printer.id, Printer.integration_type))
            printers = result.all()
        for printer_id, integration_type in printers:
            self._start(printer_id, integration_type)

    async def stop_all(self) -> None:
        for task in self._tasks.values():
            task.cancel()
        await asyncio.gather(*self._tasks.values(), return_exceptions=True)
