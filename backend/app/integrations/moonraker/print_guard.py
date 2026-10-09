"""Safeguards for the orders that change a print from the web: resume and cancel.

On this project's printer a resume has already ended badly once (a "Move out of range" error right
after one, see docs/laboratorio/RESULTADOS.md); whether the order reached the printer twice could not
be told afterwards. So the web's resume and cancel go through here:

  - one order at a time per printer (resume and cancel share the same lock): a second click while the
    first is in flight is refused;
  - no new order of the same kind while the previous one is still being carried out (the printer has not answered it
    yet; at most IN_PROGRESS_SECONDS): a resume takes 45 to 65 s and its state stays "paused" until it ends, so a
    second click in that time would otherwise pass the state check below;
  - no new order of the same kind within COOLDOWN_SECONDS of the last one, whatever its outcome (an
    order that timed out may still have reached the printer);
  - the order is only sent if the printer itself says it is in a state where it makes sense right now
    (a read-only GET of print_stats.state), not what PrintWatch last saw: resume needs `paused`; cancel
    needs `printing` or `paused`. In any other state - error, standby, complete - nothing is sent.

The order goes out in the background and the functions here return it (a PendingAction) as soon as it is sent:
the printer answers a resume 45 to 65 s later, and that wait is not the guard's to hold (the lock covers the decision
and noting the order, not the printer's answer).

Cancel cannot be undone, so its endpoint also requires the typed confirmation (see api/v1/printers.py)."""

import asyncio

import httpx

from app.integrations.moonraker import command_log
from app.integrations.moonraker.client import PendingAction, start_print_action

RESUME_COOLDOWN_SECONDS = 20.0
CANCEL_COOLDOWN_SECONDS = 20.0
# Longest time a resume or cancel is considered "still being carried out": the longest resume seen took 65 s.
RESUME_IN_PROGRESS_SECONDS = 90.0
CANCEL_IN_PROGRESS_SECONDS = 90.0
_STATE_TIMEOUT_SECONDS = 5.0

_locks: dict[str, asyncio.Lock] = {}


class ActionRefused(Exception):
    """The order was not sent; str() says why, in words the web can show."""


class ResumeRefused(ActionRefused):
    pass


class CancelRefused(ActionRefused):
    pass


async def read_print_state(base_url: str) -> str | None:
    """print_stats.state straight from the printer (GET only). Raises httpx.HTTPError if unreachable."""
    async with httpx.AsyncClient(timeout=_STATE_TIMEOUT_SECONDS) as client:
        response = await client.get(f"{base_url}/printer/objects/query", params={"print_stats": "state"})
        response.raise_for_status()
    return (((response.json().get("result") or {}).get("status") or {}).get("print_stats") or {}).get("state")


async def _send_guarded(
    base_url: str,
    action: str,
    requested_by: str | None,
    *,
    allowed_states: tuple[str, ...],
    cooldown_seconds: float,
    in_progress_seconds: float,
    refusal: type[ActionRefused],
    verb: str,
    wrong_state: str,
) -> PendingAction:
    lock = _locks.setdefault(base_url, asyncio.Lock())
    if lock.locked():  # checked and taken with no await in between: atomic in the event loop
        raise refusal("Ya hay una orden en curso para esta impresora; espera a que termine.")
    async with lock:
        running = command_log.in_progress(base_url, action, in_progress_seconds)
        if running is not None:
            raise refusal(
                f"La orden de {verb} que se pidió hace {running.age_seconds:.0f} s sigue en curso: la impresora tarda "
                "hasta un minuto en terminar. Espera a que cambie de estado; no hace falta repetirla."
            )
        recent = command_log.recent(base_url, action, cooldown_seconds)
        if recent is not None:
            raise refusal(
                f"Se pidió {verb} hace {recent.age_seconds:.0f} s; espera unos segundos y revisa el estado de la impresora antes de repetir."
            )
        state = await read_print_state(base_url)
        if state not in allowed_states:
            raise refusal(f"{wrong_state} (estado: {state or 'desconocido'}); no se envió la orden.")
        return start_print_action(base_url, action, requested_by=requested_by)


async def resume_safely(base_url: str, requested_by: str | None) -> PendingAction:
    return await _send_guarded(
        base_url, "resume", requested_by,
        allowed_states=("paused",), cooldown_seconds=RESUME_COOLDOWN_SECONDS,
        in_progress_seconds=RESUME_IN_PROGRESS_SECONDS, refusal=ResumeRefused,
        verb="reanudar", wrong_state="La impresora no está en pausa",
    )


async def cancel_safely(base_url: str, requested_by: str | None) -> PendingAction:
    return await _send_guarded(
        base_url, "cancel", requested_by,
        allowed_states=("printing", "paused"), cooldown_seconds=CANCEL_COOLDOWN_SECONDS,
        in_progress_seconds=CANCEL_IN_PROGRESS_SECONDS, refusal=CancelRefused,
        verb="cancelar", wrong_state="La impresora no está imprimiendo ni en pausa",
    )
