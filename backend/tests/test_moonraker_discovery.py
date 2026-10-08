import argparse
import asyncio
import json

import httpx
import pytest


def _in_process(discovery, mock):
    """A discovery client whose requests go straight to the simulated printer's app."""
    moon = discovery.ReadOnlyMoonraker("http://mock-printer:7125", timeout=5)
    moon._client = httpx.AsyncClient(transport=httpx.ASGITransport(app=mock.app))
    return moon


def _ctx():
    return {"args": argparse.Namespace(all_logs=False, max_log_mb=1, gcode_file=[])}


def test_only_read_endpoints_are_allowed(discovery):
    moon = discovery.ReadOnlyMoonraker("http://printer:7125", timeout=1)
    for path in (
        "/printer/print/pause",
        "/printer/print/resume",
        "/printer/print/cancel",
        "/printer/gcode/script",
        "/printer/emergency_stop",
        "/printer/firmware_restart",
        "/machine/reboot",
        "/server/files/delete",
    ):
        with pytest.raises(ValueError):
            moon._check_allowed("http://printer:7125" + path, api=True)
    moon._check_allowed("http://printer:7125/printer/objects/query", api=True)


def test_webcam_urls_cannot_reach_the_api_or_other_hosts(discovery):
    moon = discovery.ReadOnlyMoonraker("http://printer:7125", timeout=1)
    with pytest.raises(ValueError):
        moon._check_allowed("http://printer/printer/gcode/script?script=G28", api=False)
    with pytest.raises(ValueError):
        moon._check_allowed("http://elsewhere/webcam/?action=snapshot", api=False)
    moon._check_allowed("http://printer:4408/webcam/?action=snapshot", api=False)


def test_websocket_refuses_write_methods_before_sending_anything(discovery):
    class NoSocket:
        async def send(self, _message):
            raise AssertionError("nothing should be sent")

    rpc = discovery._ReadOnlyRpc(NoSocket())
    for method in ("printer.gcode.script", "printer.print.pause", "printer.print.resume", "printer.emergency_stop"):
        with pytest.raises(ValueError):
            asyncio.run(rpc.call(method))


def test_relative_webcam_urls_try_the_web_ports_first(discovery):
    moon = discovery.ReadOnlyMoonraker("http://192.168.10.22:7125", timeout=1)
    urls, note = discovery._webcam_candidates(moon, "/webcam/?action=stream")
    assert urls == [
        "http://192.168.10.22/webcam/?action=stream",
        "http://192.168.10.22:4408/webcam/?action=stream",
        "http://192.168.10.22:7125/webcam/?action=stream",
    ]
    assert note is None
    assert discovery._webcam_candidates(moon, "rtsp://192.168.10.22/live")[0] == []
    assert discovery._webcam_candidates(moon, "http://10.0.0.5/stream")[0] == []


def test_klippy_excerpt_starts_before_the_pause_and_reads_the_file_position(discovery):
    lines = ["Start printer at Thu Sep 25 15:50:01 2026 (1758833401.0 39.6)"]
    lines += [f"Stats {eventtime:.1f}: gcodein=0" for eventtime in range(12300, 12401, 20)]
    lines += ["Move out of range: 292.424 249.610 28.401 [18941.126]", "Exiting SD card print (position 1234567)"]

    excerpt, position = discovery._klippy_incident_excerpt(lines)

    assert excerpt[0] == "Stats 12380.0: gcodein=0"
    assert excerpt[-1] == "Exiting SD card print (position 1234567)"
    assert position == 1234567


def test_klippy_excerpt_is_empty_without_the_incident(discovery):
    assert discovery._klippy_incident_excerpt(["Stats 100.0: gcodein=0", "Move out of range: 1 2 3 [4]"]) == ([], None)


def test_moonraker_excerpt_keeps_print_control_requests_with_context(discovery):
    lines = [f"line {index}" for index in range(20)]
    lines[5] = "200 POST /printer/print/resume (192.168.10.100) [_TRUSTED_USER_] 45.67ms"
    lines[15] = "200 POST /printer/print/pause (192.168.10.100) [_TRUSTED_USER_] 12.00ms"

    excerpt = discovery._moonraker_incident_excerpt(lines)

    assert excerpt == [*lines[2:9], "...", *lines[12:19]]


def test_out_of_range_moves_ignore_relative_mode(discovery):
    lines = ["G90", "G1 X100 Y100", "G1 X292.4 Y249.6", "G91", "G1 X300", "G90", "G0 Y261"]
    assert discovery._out_of_range_moves(lines, {"x": 260.0, "y": 260.0}) == ["G1 X292.4 Y249.6", "G0 Y261"]


def test_redact_hides_serials_and_mac_addresses(discovery):
    data = {"cpu_info": {"serial_number": "abc", "model": "x"}, "network": {"wlan0": {"mac_address": "aa", "ip": []}}}
    redacted = discovery._redact(data)
    assert redacted["cpu_info"] == {"serial_number": "<oculto>", "model": "x"}
    assert redacted["network"]["wlan0"] == {"mac_address": "<oculto>", "ip": []}


def test_discovery_steps_against_the_simulated_printer(discovery, mock_moonraker, tmp_path):
    printer = mock_moonraker.printer
    printer.start(mock_moonraker.MOCK_FILE)
    for _ in range(2000):
        if printer.layer >= 1:
            break
        printer.tick(0.05)
    printer.run_gcode("M104 S245")
    printer.fail(292.424, 249.610, 28.401)
    ctx = _ctx()

    async def scenario():
        moon = _in_process(discovery, mock_moonraker)
        try:
            return (
                await discovery._save_gcode_store(moon, tmp_path),
                await discovery._save_logs(moon, tmp_path, ctx),
                await discovery._save_history(moon, tmp_path, ctx),
                await discovery._save_objects(moon, tmp_path, ctx),
                await discovery._analyze_config(tmp_path, ctx),
                await discovery._save_gcode_files(moon, tmp_path, ctx),
                await discovery._save_machine(moon, tmp_path),
            ), moon.requests
        finally:
            await moon.close()

    (store, logs, history, objects, config, gcode, machine), requests = asyncio.run(scenario())

    assert store["lineas"] >= 2  # the M104 and the error
    assert logs["incidente_en_klippy_log"] is True
    assert logs["posicion_del_error_en_el_gcode"] is not None
    assert history["trabajos"] == 2
    assert objects["no_reconocidos"] == []
    assert "gcode_macro PAUSE" in config["macros_relevantes"]
    assert gcode["revisados"] == {"BOX FINAL lista pa imprimir_PETG_2h5m.gcode": False, "mock_box.gcode": True}
    assert (tmp_path / "gcode" / "mock_box.gcode.final.gcode").read_text().rstrip().endswith("END_PRINT")
    assert machine["ok"] is True
    system_info = json.loads((tmp_path / "system_info.json").read_text(encoding="utf-8"))
    assert system_info["system_info"]["cpu_info"]["serial_number"] == "<oculto>"
    assert all("error" not in request for request in requests)


def test_discovery_stops_when_the_printer_asks_for_credentials(discovery, mock_moonraker, tmp_path):
    mock_moonraker.auth_required_prefixes = ("/server/files/logs",)

    async def scenario():
        moon = _in_process(discovery, mock_moonraker)
        try:
            await discovery._save_logs(moon, tmp_path, _ctx())
        finally:
            await moon.close()

    with pytest.raises(discovery.AuthenticationRequired):
        asyncio.run(scenario())
