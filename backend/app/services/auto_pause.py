import asyncio
import logging
from datetime import datetime, timedelta, timezone

import httpx

from app.db.models import JobStatus, Printer, PrinterStatus, PrintJob
from app.integrations.moonraker.client import send_print_action
from app.services.streak_detection import check_consecutive_streak
from app.ws.manager import manager

logger = logging.getLogger(__name__)

# Same value as jam_detection.py's under_extrusion threshold, on purpose: there is no data
# justifying a different number for spaghetti specifically, so this reuses the one criterion
# the project already has for "how many consecutive layers make a trend, not a blip" rather
# than inventing a second number. Tune here if that ever changes - not inline in the logic.
_SPAGHETTI_STREAK_THRESHOLD = 3
_GRACE_PERIOD_SECONDS = 15


class AutoPauseManager:
    """At most one pending auto-pause per job, tracked entirely in memory. The grace-period
    countdown IS a live asyncio.Task in this process regardless of where its existence is
    recorded, so tracking 'is one pending' here (instead of in Postgres) avoids a second source
    of truth for the same fact. Trade-off: a backend restart mid-countdown silently drops the
    pending pause (documented in docs/KNOWN_LIMITATIONS.md) - accepted because the window is only
    15s and this is a safety/demo feature, not durable infrastructure."""

    def __init__(self) -> None:
        self._pending: dict[int, asyncio.Task] = {}  # job_id -> countdown task

    async def check_spaghetti_streak(self, db_session_factory, job_id: int, camera_id: int, printer_id: int) -> None:
        if job_id in self._pending:
            # Grace period already running for this job - do NOT reset it just because the
            # streak continues. Otherwise a print that keeps producing spaghetti every layer
            # would never actually reach the deadline.
            return

        async with db_session_factory() as db:
            triggered = await check_consecutive_streak(
                db, job_id, camera_id, "spaghetti", _SPAGHETTI_STREAK_THRESHOLD
            )
            if not triggered:
                return

            printer = await db.get(Printer, printer_id)
            if printer is not None and printer.last_known_status == PrinterStatus.paused:
                logger.info(
                    "Spaghetti streak on job %s, but printer %s is already paused - not scheduling", job_id, printer_id
                )
                return

        executes_at = datetime.now(timezone.utc) + timedelta(seconds=_GRACE_PERIOD_SECONDS)
        logger.warning(
            "Spaghetti streak (%s consecutive layers) on job %s (printer %s) - auto-pause scheduled for %s "
            "unless aborted",
            _SPAGHETTI_STREAK_THRESHOLD,
            job_id,
            printer_id,
            executes_at.isoformat(),
        )
        self._pending[job_id] = asyncio.create_task(self._run_countdown(db_session_factory, job_id, printer_id, executes_at))
        await manager.broadcast(
            "auto_pause.pending",
            {
                "job_id": job_id,
                "printer_id": printer_id,
                "reason": "spaghetti",
                "consecutive_layers": _SPAGHETTI_STREAK_THRESHOLD,
                "executes_at": executes_at.isoformat(),
            },
        )

    async def abort(self, job_id: int) -> bool:
        task = self._pending.get(job_id)
        if task is None or task.done():
            return False
        task.cancel()
        await manager.broadcast("auto_pause.aborted", {"job_id": job_id})
        logger.info("Auto-pause for job %s aborted by user", job_id)
        return True

    async def cancel_all(self) -> None:
        """Backend shutdown: don't leave orphaned countdown tasks - see the class docstring for
        why a countdown in flight is simply lost, not resumed, on the next startup."""
        for task in self._pending.values():
            task.cancel()
        await asyncio.gather(*self._pending.values(), return_exceptions=True)
        self._pending.clear()

    async def _run_countdown(self, db_session_factory, job_id: int, printer_id: int, executes_at: datetime) -> None:
        try:
            delay = (executes_at - datetime.now(timezone.utc)).total_seconds()
            await asyncio.sleep(max(0.0, delay))
            await self._execute(db_session_factory, job_id, printer_id)
        except asyncio.CancelledError:
            logger.info("Auto-pause countdown for job %s cancelled", job_id)
            raise
        finally:
            self._pending.pop(job_id, None)

    async def _execute(self, db_session_factory, job_id: int, printer_id: int) -> None:
        async with db_session_factory() as db:
            job = await db.get(PrintJob, job_id)
            printer = await db.get(Printer, printer_id)

            if job is None or job.status != JobStatus.running:
                logger.info("Auto-pause for job %s skipped: job is no longer running", job_id)
                return
            if printer is None:
                logger.warning("Auto-pause for job %s skipped: printer %s not found", job_id, printer_id)
                return
            if printer.last_known_status == PrinterStatus.paused:
                logger.info("Auto-pause for job %s skipped: printer %s already paused", job_id, printer_id)
                return

            base_url = printer.octoprint_url

        logger.warning("Executing auto-pause for job %s (printer %s) via Moonraker at %s", job_id, printer_id, base_url)
        try:
            await send_print_action(base_url, "pause")
        except httpx.HTTPError:
            logger.exception("Auto-pause HTTP call to Moonraker failed for job %s (printer %s)", job_id, printer_id)
            await manager.broadcast(
                "auto_pause.failed",
                {
                    "job_id": job_id,
                    "printer_id": printer_id,
                    "reason": "No se pudo contactar a la impresora para pausarla - revisar la conexión de red",
                },
            )
            return

        logger.warning("Auto-pause executed for job %s (printer %s)", job_id, printer_id)
        # printer.last_known_status flips to 'paused' on its own once the Moonraker listener sees
        # Klipper report print_stats.state == 'paused' (_STATE_TO_PRINTER_STATUS already maps
        # that) - no need to set it here and risk disagreeing with what Klipper actually did.
        await manager.broadcast("auto_pause.executed", {"job_id": job_id, "printer_id": printer_id, "reason": "spaghetti"})


auto_pause_manager = AutoPauseManager()
