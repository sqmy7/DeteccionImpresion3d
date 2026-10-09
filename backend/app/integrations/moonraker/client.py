import httpx

from app.integrations.moonraker import command_log

_TIMEOUT_SECONDS = 10


async def send_print_action(base_url: str, action: str, requested_by: str | None = None) -> None:
    """POST http://<base_url>/printer/print/<action> - pause/resume/cancel, Moonraker's documented,
    stable print-control API (the same one Fluidd/Mainsail use). Raises httpx.HTTPError on any
    failure (unreachable printer, non-2xx response) - callers decide what that means for them.

    Every attempt, successful or not, is noted in command_log so the event log can attribute the
    resulting state change to PrintWatch. It is noted before it is sent (the printer changes state before it
    answers) and completed with the outcome. requested_by names who asked (None for the auto-pause)."""
    command = command_log.begin(base_url, action, requested_by)
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT_SECONDS) as client:
            response = await client.post(f"{base_url}/printer/print/{action}")
            response.raise_for_status()
    except httpx.HTTPError as error:
        command_log.finish(command, ok=False, error=f"{type(error).__name__}: {error}")
        raise
    command_log.finish(command, ok=True)
