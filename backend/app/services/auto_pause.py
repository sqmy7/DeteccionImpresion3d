import asyncio
import logging
import time
from datetime import datetime, timedelta, timezone

import httpx

from app.core.config import settings
from app.db.models import JobStatus, Printer, PrinterStatus, PrintJob
from app.integrations.moonraker.client import send_print_action
from app.integrations.moonraker.print_guard import read_print_state
from app.services import incidents
from app.services.printer_events import EventOrigin, record_event
from app.services.streak_detection import check_consecutive_streak
from app.ws.manager import manager

logger = logging.getLogger(__name__)

# Same value as jam_detection.py's under_extrusion threshold, on purpose: there is no data
# justifying a different number for spaghetti specifically, so this reuses the one criterion
# the project already has for "how many consecutive layers make a trend, not a blip" rather
# than inventing a second number. Tune here if that ever changes - not inline in the logic.
_SPAGHETTI_STREAK_THRESHOLD = 3
_GRACE_PERIOD_SECONDS = 15
# After the pause is sent, how long to wait for Klipper itself to say "paused" (read-only GETs of
# print_stats.state) before calling it "pausa no confirmada".
_CONFIRM_TIMEOUT_SECONDS = 20.0
_CONFIRM_POLL_SECONDS = 1.0


class AutoPauseManager:
    """What happens when the spaghetti streak is reached depends on settings.auto_pause_mode (read on
    every check, so tests and the .env agree): "on" is the countdown below; "warn" announces and logs
    an auto_pause.would_pause event and nothing else; "off" does nothing.

    Every step is also written to the event log (auto_pause.pending / aborted / confirmed / not_confirmed,
    would_pause) and to the incident of the job (app/services/incidents.py), whose failures never get in the
    way of the pause itself.

    At most one pending auto-pause per job, tracked entirely in memory. The grace-period
    countdown IS a live asyncio.Task in this process regardless of where its existence is
    recorded, so tracking 'is one pending' here (instead of in Postgres) avoids a second source
    of truth for the same fact. Trade-off: a backend restart mid-countdown silently drops the
    pending pause (documented in docs/KNOWN_LIMITATIONS.md) - accepted because the window is only
    15s and this is a safety/demo feature, not durable infrastructure."""

    def __init__(self) -> None:
        self._pending: dict[int, asyncio.Task] = {}  # job_id -> countdown task (and then the confirmation)
        self._counting_down: set[int] = set()  # jobs still within the grace period: the only ones that can be aborted
        self._meta: dict[int, dict] = {}  # job_id -> printer_id, camera_id, incident_id, db factory

    async def check_spaghetti_streak(self, db_session_factory, job_id: int, camera_id: int, printer_id: int) -> None:
        mode = settings.auto_pause_mode
        if mode == "off":
            return
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
            streak = await incidents.streak_items(db, job_id, camera_id, _SPAGHETTI_STREAK_THRESHOLD)

        if mode == "warn":
            await self._would_pause(db_session_factory, job_id, camera_id, printer_id, streak)
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
        opened = await self._safe(
            "open the incident",
            incidents.open_incident(
                db_session_factory, job_id=job_id, printer_id=printer_id, camera_id=camera_id, defect_class="spaghetti",
                reason="auto_pause", streak=streak, detection_id=streak[-1]["detection_id"] if streak else None, announced=True,
            ),
        )
        incident_id = opened[0] if opened else None
        self._meta[job_id] = {
            "factory": db_session_factory, "printer_id": printer_id, "camera_id": camera_id, "incident_id": incident_id,
        }
        await self._safe(
            "log the countdown",
            record_event(
                db_session_factory, printer_id, "auto_pause.pending", EventOrigin.MONITOR, job_id=job_id,
                detail={
                    "incident_id": incident_id, "reason": "spaghetti", "mode": "on", "grace_seconds": _GRACE_PERIOD_SECONDS,
                    "executes_at": executes_at.isoformat(), "streak": list(reversed(streak)),
                },
            ),
        )
        self._counting_down.add(job_id)
        self._pending[job_id] = asyncio.create_task(self._run_countdown(db_session_factory, job_id, printer_id, executes_at))
        await manager.broadcast(
            "auto_pause.pending",
            {
                "job_id": job_id,
                "printer_id": printer_id,
                "incident_id": incident_id,
                "reason": "spaghetti",
                "consecutive_layers": _SPAGHETTI_STREAK_THRESHOLD,
                "executes_at": executes_at.isoformat(),
            },
        )

    async def _would_pause(self, db_session_factory, job_id: int, camera_id: int, printer_id: int, streak: list[dict]) -> None:
        """Warn mode: say the pause would have been sent, with the layer and the model's confidence,
        and send nothing to the printer."""
        newest_first = list(reversed(streak))
        last = newest_first[0] if newest_first else {}
        logger.warning(
            "Spaghetti streak (%s consecutive layers) on job %s (printer %s): auto-pause would have fired "
            "(AUTO_PAUSE_MODE=warn, nothing sent)",
            _SPAGHETTI_STREAK_THRESHOLD, job_id, printer_id,
        )
        opened = await self._safe(
            "open the incident",
            incidents.open_incident(
                db_session_factory, job_id=job_id, printer_id=printer_id, camera_id=camera_id, defect_class="spaghetti",
                reason="would_pause", streak=streak, detection_id=last.get("detection_id"), announced=True,
            ),
        )
        incident_id = opened[0] if opened else None
        await self._safe(
            "log would_pause",
            record_event(
                db_session_factory,
                printer_id,
                "auto_pause.would_pause",
                EventOrigin.MONITOR,
                job_id=job_id,
                detail={
                    "incident_id": incident_id,
                    "mode": "warn",
                    "sent": False,
                    "reason": "spaghetti",
                    "consecutive_layers": _SPAGHETTI_STREAK_THRESHOLD,
                    "layer": last.get("layer"),
                    "confidence": last.get("confidence"),
                    "streak": newest_first,
                },
            ),
        )
        await manager.broadcast(
            "auto_pause.would_pause",
            {
                "job_id": job_id,
                "printer_id": printer_id,
                "incident_id": incident_id,
                "reason": "spaghetti",
                "consecutive_layers": _SPAGHETTI_STREAK_THRESHOLD,
                "layer": last.get("layer"),
                "confidence": last.get("confidence"),
            },
        )

    async def abort(self, job_id: int, requested_by: str | None = None) -> bool:
        """The user stops the countdown. Only possible during the grace period: once the pause is on its
        way (or sent) there is nothing left to abort."""
        task = self._pending.get(job_id)
        if job_id not in self._counting_down or task is None or task.done():
            return False
        self._counting_down.discard(job_id)
        task.cancel()
        meta = self._meta.get(job_id) or {}
        await manager.broadcast("auto_pause.aborted", {"job_id": job_id, "incident_id": meta.get("incident_id")})
        logger.info("Auto-pause for job %s aborted by user", job_id)
        factory, printer_id = meta.get("factory"), meta.get("printer_id")
        if factory is not None and printer_id is not None:
            incident_id = meta.get("incident_id")
            if incident_id is None:  # the incident could not be opened with the countdown: open it so the abort has one
                opened = await self._safe(
                    "open the incident",
                    incidents.open_incident(
                        factory, job_id=job_id, printer_id=printer_id, camera_id=meta.get("camera_id"),
                        defect_class="spaghetti", reason="auto_pause", announced=True,
                    ),
                )
                incident_id = opened[0] if opened else None
            await self._safe(
                "log the abort",
                record_event(
                    factory, printer_id, "auto_pause.aborted", EventOrigin.MONITOR, job_id=job_id,
                    detail={"incident_id": incident_id, "requested_by": requested_by},
                ),
            )
            if incident_id is not None:
                await self._safe(
                    "close the incident",
                    incidents.close_incidents(
                        factory, incident_id=incident_id, outcome="ignored", decided_by=requested_by,
                        detail={"how": "countdown_aborted"},
                    ),
                )
        return True

    async def cancel_all(self) -> None:
        """Backend shutdown: don't leave orphaned countdown tasks - see the class docstring for
        why a countdown in flight is simply lost, not resumed, on the next startup."""
        for task in self._pending.values():
            task.cancel()
        await asyncio.gather(*self._pending.values(), return_exceptions=True)
        self._pending.clear()
        self._counting_down.clear()
        self._meta.clear()

    async def _safe(self, what: str, awaitable):
        """Incident and event-log bookkeeping must never stop a pause or a countdown."""
        try:
            return await awaitable
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Auto-pause: could not %s", what)
            return None

    async def _run_countdown(self, db_session_factory, job_id: int, printer_id: int, executes_at: datetime) -> None:
        try:
            delay = (executes_at - datetime.now(timezone.utc)).total_seconds()
            await asyncio.sleep(max(0.0, delay))
            self._counting_down.discard(job_id)  # past this point it can no longer be aborted
            await self._execute(db_session_factory, job_id, printer_id)
        except asyncio.CancelledError:
            logger.info("Auto-pause countdown for job %s cancelled", job_id)
            raise
        finally:
            self._pending.pop(job_id, None)
            self._counting_down.discard(job_id)
            self._meta.pop(job_id, None)

    async def _execute(self, db_session_factory, job_id: int, printer_id: int) -> None:
        if settings.auto_pause_mode != "on":
            logger.warning("Auto-pause for job %s not sent: AUTO_PAUSE_MODE is %s", job_id, settings.auto_pause_mode)
            return
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

        incident_id = (self._meta.get(job_id) or {}).get("incident_id")
        logger.warning("Executing auto-pause for job %s (printer %s) via Moonraker at %s", job_id, printer_id, base_url)
        sent_at = datetime.now(timezone.utc)
        if incident_id is not None:
            await self._safe("note the pause sent", incidents.mark_pause_sent(db_session_factory, incident_id, sent_at))
        try:
            await send_print_action(base_url, "pause")
        except httpx.HTTPError as error:
            logger.exception("Auto-pause HTTP call to Moonraker failed for job %s (printer %s)", job_id, printer_id)
            await self._not_confirmed(
                db_session_factory, job_id, printer_id, incident_id, reason="send_failed", error=f"{type(error).__name__}: {error}"
            )
            await manager.broadcast(
                "auto_pause.failed",
                {
                    "job_id": job_id,
                    "printer_id": printer_id,
                    "incident_id": incident_id,
                    "reason": "No se pudo contactar a la impresora para pausarla - revisar la conexión de red",
                },
            )
            return

        logger.warning("Auto-pause sent for job %s (printer %s)", job_id, printer_id)
        # "executed" means the order went out. Whether Klipper actually paused is checked next, from the
        # printer itself: printer.last_known_status flips on its own when the Moonraker listener sees
        # print_stats.state == 'paused', but that can lag or never come.
        await manager.broadcast(
            "auto_pause.executed", {"job_id": job_id, "printer_id": printer_id, "incident_id": incident_id, "reason": "spaghetti"}
        )
        await self._confirm_paused(db_session_factory, job_id, printer_id, base_url, incident_id, sent_at)

    async def _confirm_paused(
        self, db_session_factory, job_id: int, printer_id: int, base_url: str, incident_id: int | None, sent_at: datetime
    ) -> None:
        """Asks the printer itself (a read-only GET) whether it is paused, for up to _CONFIRM_TIMEOUT_SECONDS."""
        deadline = time.monotonic() + _CONFIRM_TIMEOUT_SECONDS
        last_state: str | None = None
        while True:
            try:
                last_state = await read_print_state(base_url)
            except httpx.HTTPError:
                last_state = None
            if last_state == "paused":
                seconds = round((datetime.now(timezone.utc) - sent_at).total_seconds(), 1)
                await self._safe(
                    "log the confirmation",
                    record_event(
                        db_session_factory, printer_id, "auto_pause.confirmed", EventOrigin.MONITOR, job_id=job_id,
                        detail={"incident_id": incident_id, "seconds_after_sending": seconds},
                    ),
                )
                if incident_id is not None:
                    await self._safe(
                        "note the pause confirmed",
                        incidents.mark_paused(db_session_factory, incident_id=incident_id, origin="printwatch", order={"source": "auto_pause"}),
                    )
                await manager.broadcast(
                    "auto_pause.confirmed", {"job_id": job_id, "printer_id": printer_id, "incident_id": incident_id, "seconds": seconds}
                )
                return
            if time.monotonic() >= deadline:
                break
            await asyncio.sleep(_CONFIRM_POLL_SECONDS)
        await self._not_confirmed(
            db_session_factory, job_id, printer_id, incident_id, reason="timeout", last_state=last_state or "sin respuesta"
        )

    async def _not_confirmed(self, db_session_factory, job_id: int, printer_id: int, incident_id: int | None, **detail) -> None:
        logger.error("Auto-pause for job %s (printer %s) NOT confirmed: %s", job_id, printer_id, detail)
        await self._safe(
            "log the missing confirmation",
            record_event(
                db_session_factory, printer_id, "auto_pause.not_confirmed", EventOrigin.MONITOR, job_id=job_id,
                detail={"incident_id": incident_id, "timeout_seconds": _CONFIRM_TIMEOUT_SECONDS, **detail},
            ),
        )
        if incident_id is not None:
            await self._safe("note the pause not confirmed", incidents.mark_unconfirmed(db_session_factory, incident_id, **detail))
        await manager.broadcast(
            "auto_pause.not_confirmed", {"job_id": job_id, "printer_id": printer_id, "incident_id": incident_id, **detail}
        )


auto_pause_manager = AutoPauseManager()
