import httpx


class OctoPrintClient:
    """Thin async wrapper over OctoPrint's REST API for a single printer."""

    def __init__(self, base_url: str, api_key: str) -> None:
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key

    async def login(self) -> dict:
        """POST /api/login (passive) - exchanges the API key for a {name, session} pair
        used to authenticate the push WebSocket connection."""
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                f"{self._base_url}/api/login",
                headers={"X-Api-Key": self._api_key},
                json={"passive": True},
            )
            response.raise_for_status()
            return response.json()

    async def get_job(self) -> dict:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(f"{self._base_url}/api/job", headers={"X-Api-Key": self._api_key})
            response.raise_for_status()
            return response.json()

    async def get_printer_state(self) -> dict:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(f"{self._base_url}/api/printer", headers={"X-Api-Key": self._api_key})
            response.raise_for_status()
            return response.json()
