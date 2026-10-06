"""Minimal stand-in for a real OctoPrint instance, for testing the backend's OctoPrint
client/listener without physical hardware. Replicates the wire shapes our client depends on:
POST /api/login, GET /api/job, GET /api/printer, and the /sockjs/websocket push protocol
(connected greeting -> client sends {"auth": ...} -> server streams "current" state updates
and DisplayLayerProgress "plugin" messages simulating an advancing print).

Not a general-purpose OctoPrint simulator - only implements what this project's client uses.
"""

import asyncio
import json

import uvicorn
from fastapi import FastAPI, Header, HTTPException, WebSocket, WebSocketDisconnect

MOCK_API_KEY = "mock-api-key"
LAYER_INTERVAL_SECONDS = 2

app = FastAPI()


def _check_api_key(x_api_key: str | None) -> None:
    if x_api_key != MOCK_API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API key")


@app.post("/api/login")
async def login(x_api_key: str | None = Header(default=None, alias="X-Api-Key")) -> dict:
    _check_api_key(x_api_key)
    return {"name": "mock-user", "session": "mock-session-token"}


@app.get("/api/job")
async def get_job(x_api_key: str | None = Header(default=None, alias="X-Api-Key")) -> dict:
    _check_api_key(x_api_key)
    return {
        "job": {"file": {"name": "mock.gcode"}},
        "progress": {"completion": 42.0},
        "state": "Printing",
    }


@app.get("/api/printer")
async def get_printer(x_api_key: str | None = Header(default=None, alias="X-Api-Key")) -> dict:
    _check_api_key(x_api_key)
    return {
        "state": {
            "text": "Printing",
            "flags": {
                "operational": True,
                "printing": True,
                "paused": False,
                "error": False,
                "closedOrError": False,
            },
        }
    }


@app.websocket("/sockjs/websocket")
async def octoprint_ws(websocket: WebSocket) -> None:
    await websocket.accept()
    await websocket.send_text(json.dumps({"connected": {"version": "1.9.0", "session": "mock-session-token"}}))

    try:
        auth_raw = await websocket.receive_text()
        auth_message = json.loads(auth_raw)
        if auth_message.get("auth") != "mock-user:mock-session-token":
            await websocket.close(code=4001, reason="Bad auth")
            return

        layer_number = 0
        while True:
            await websocket.send_text(
                json.dumps(
                    {
                        "current": {
                            "state": {
                                "text": "Printing",
                                "flags": {
                                    "operational": True,
                                    "printing": True,
                                    "paused": False,
                                    "error": False,
                                    "closedOrError": False,
                                },
                            }
                        }
                    }
                )
            )
            await websocket.send_text(
                json.dumps(
                    {
                        "plugin": {
                            "plugin": "DisplayLayerProgress",
                            "data": {
                                "currentLayer": layer_number,
                                "currentHeight": round(layer_number * 0.2, 2),
                            },
                        }
                    }
                )
            )
            layer_number += 1
            await asyncio.sleep(LAYER_INTERVAL_SECONDS)
    except WebSocketDisconnect:
        pass


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=5000)
