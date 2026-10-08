"""Safeguards for resuming a print from the web.

On this project's printer a resume has already ended badly once (a "Move out of range" error right
after one, see docs/laboratorio/RESULTADOS.md); whether the order reached the printer twice could not
be told afterwards. So the web's resume goes through here:

  - one resume at a time per printer: a second click while the first is in flight is refused;
  - no new resume within RESUME_COOLDOWN_SECONDS of the last one, whatever its outcome (an order that
    timed out may still have reached the printer);
  - the order is only sent if the printer itself says it is paused right now (a read-only GET of
    print_stats.state), not what PrintWatch last saw: if it is printing, in error or anything else, the
    order is not sent.
"""

import asyncio

import httpx

from app.integrations.moonraker import command_log
from app.integrations.moonraker.client import send_print_action

RESUME_COOLDOWN_SECONDS = 20.0
_STATE_TIMEOUT_SECONDS = 5.0

_locks: dict[str, asyncio.Lock] = {}


class ResumeRefused(Exception):
    """The resume was not sent; str() says why, in words the web can show."""


async def read_print_state(base_url: str) -> str | None:
    """print_stats.state straight from the printer (GET only). Raises httpx.HTTPError if unreachable."""
    async with httpx.AsyncClient(timeout=_STATE_TIMEOUT_SECONDS) as client:
        response = await client.get(f"{base_url}/printer/objects/query", params={"print_stats": "state"})
        response.raise_for_status()
    return (((response.json().get("result") or {}).get("status") or {}).get("print_stats") or {}).get("state")


async def resume_safely(base_url: str, requested_by: str | None) -> None:
    lock = _locks.setdefault(base_url, asyncio.Lock())
    if lock.locked():  # checked and taken with no await in between: atomic in the event loop
        raise ResumeRefused("Ya hay una orden de reanudar en curso para esta impresora; espera a que termine.")
    async with lock:
        recent = command_log.recent(base_url, "resume", RESUME_COOLDOWN_SECONDS)
        if recent is not None:
            raise ResumeRefused(
                f"Se pidió reanudar hace {recent.age_seconds:.0f} s; espera unos segundos y revisa el estado de la impresora antes de repetir."
            )
        state = await read_print_state(base_url)
        if state != "paused":
            raise ResumeRefused(f"La impresora no está en pausa (estado: {state or 'desconocido'}); no se envió la orden.")
        await send_print_action(base_url, "resume", requested_by=requested_by)
