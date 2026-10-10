import asyncio
import logging
from dataclasses import dataclass

import httpx

from app.integrations.moonraker import command_log

logger = logging.getLogger(__name__)

_CONNECT_TIMEOUT_SECONDS = 10
# Moonraker answers pause/resume/cancel when the printer's macro has ended, not when it accepted the order: about 9 s
# for a pause and 45 to 65 s for a resume on the Creality Hi (measured 2026-10-09). With a 10 s limit the answer was
# cut off ("ReadTimeout") although the printer did what it was told.
_ANSWER_TIMEOUT_SECONDS = 120

_background: set[asyncio.Task] = set()  # tasks must be referenced or they can be collected mid-flight


@dataclass
class PendingAction:
    """An order on its way to the printer. `task` ends with None, or with the httpx error that stopped it."""

    command: command_log.SentCommand
    task: "asyncio.Task[httpx.HTTPError | None]"


async def _post(base_url: str, action: str, command: command_log.SentCommand) -> httpx.HTTPError | None:
    timeout = httpx.Timeout(_ANSWER_TIMEOUT_SECONDS, connect=_CONNECT_TIMEOUT_SECONDS)
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(f"{base_url}/printer/print/{action}")
            response.raise_for_status()
    except httpx.HTTPError as error:
        command_log.finish(command, ok=False, error=f"{type(error).__name__}: {error}")
        logger.warning("Moonraker '%s' order to %s failed: %s %s", action, base_url, type(error).__name__, error)
        return error
    command_log.finish(command, ok=True)
    return None


def start_print_action(base_url: str, action: str, requested_by: str | None = None) -> PendingAction:
    """Notes the order and sends it in the background; returns at once. The caller decides how long to wait for the
    answer (the web waits a few seconds for a quick refusal and then reports the order as accepted: the printer's
    own state change is the confirmation)."""
    command = command_log.begin(base_url, action, requested_by)
    task = asyncio.create_task(_post(base_url, action, command))
    _background.add(task)
    task.add_done_callback(_background.discard)
    return PendingAction(command, task)


async def send_print_action(base_url: str, action: str, requested_by: str | None = None) -> None:
    """POST http://<base_url>/printer/print/<action> - pause/resume/cancel, Moonraker's documented,
    stable print-control API (the same one Fluidd/Mainsail use), waiting for the printer's answer. Raises
    httpx.HTTPError on any failure (unreachable printer, non-2xx response) - callers decide what that means for them.

    Every attempt, successful or not, is noted in command_log so the event log can attribute the
    resulting state change to PrintWatch. It is noted before it is sent (the printer changes state before it
    answers) and completed with the outcome. requested_by names who asked (None for the auto-pause)."""
    pending = start_print_action(base_url, action, requested_by)
    error = await asyncio.shield(pending.task)  # if the caller is cancelled the order still finishes and is noted
    if error is not None:
        raise error
