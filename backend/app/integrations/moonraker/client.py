import httpx

_TIMEOUT_SECONDS = 10


async def send_print_action(base_url: str, action: str) -> None:
    """POST http://<base_url>/printer/print/<action> - pause/resume/cancel, Moonraker's documented,
    stable print-control API (the same one Fluidd/Mainsail use). Raises httpx.HTTPError on any
    failure (unreachable printer, non-2xx response) - callers decide what that means for them."""
    async with httpx.AsyncClient(timeout=_TIMEOUT_SECONDS) as client:
        response = await client.post(f"{base_url}/printer/print/{action}")
        response.raise_for_status()
