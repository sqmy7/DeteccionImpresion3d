"""The camera URL finder: pure parsing helpers, and a run against a local fake web interface."""

import asyncio
import http.server
import json
import threading

import pytest

from conftest import load_script

finder = load_script("find_camera_urls")

JS = 'const cam = {stream: "http://192.168.10.50:8080/?action=stream", snap: "/webcam/?action=snapshot", other: "/api/files"};'


def test_candidates_pick_only_camera_like_addresses():
    found = finder.camera_candidates(JS + " var x = 'rtsp://h/live'; var y = \"/server/files/list\";")
    assert found == ["http://192.168.10.50:8080/?action=stream", "/webcam/?action=snapshot", "rtsp://h/live"]


def test_linked_assets_stay_on_the_printer_host():
    html = '<script src="/js/app.js"></script><link href="style.css"><script src="https://cdn.example.com/x.js"></script><img src="logo.png">'
    assert finder.linked_assets(html, "http://10.0.0.5/", "10.0.0.5") == ["http://10.0.0.5/js/app.js", "http://10.0.0.5/style.css"]


def test_ports_mentioned_only_for_the_printer_itself():
    texts = ['{"a": "http://10.0.0.5:8080/x", "b": "http://other:9000/y", "c": "http://localhost:4408"}']
    assert finder.ports_mentioned(texts, "10.0.0.5") == [8080, 4408]


def test_the_reader_refuses_other_hosts():
    reader = finder.Reader("10.0.0.5", None)
    with pytest.raises(ValueError):
        asyncio.run(reader.get("http://example.com/"))


def _serve(pages: dict, seen: list[str]):
    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            seen.append(self.path.split("?")[0])
            kind, body = pages.get(self.path.split("?")[0], (None, None))
            self.send_response(404 if body is None else 200)
            if body is not None:
                self.send_header("Content-Type", kind)
            self.end_headers()
            if body is not None:
                self.wfile.write(body)

        def log_message(self, *args):
            pass

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, server.server_address[1]


def test_find_reads_the_web_interface_and_reports_where_each_url_came_from(tmp_path, monkeypatch):
    web_seen, api_seen = [], []
    web, web_port = _serve(
        {"/": ("text/html", b'<html><script src="/app.js"></script><img src="/logo.png"></html>'), "/app.js": ("application/javascript", JS.encode())},
        web_seen,
    )
    # Moonraker's own answers mention the web interface's port, which is how the finder learns it.
    api, api_port = _serve(
        {
            "/server/webcams/list": ("application/json", json.dumps({"result": {"webcams": []}}).encode()),
            "/server/info": ("application/json", json.dumps({"web": f"http://127.0.0.1:{web_port}/"}).encode()),
        },
        api_seen,
    )
    monkeypatch.setattr(finder, "MOONRAKER_PORT", api_port)
    try:
        report = asyncio.run(finder.find("127.0.0.1", tmp_path, None, 10))
    finally:
        web.shutdown()
        api.shutdown()
    urls = {item["url"]: item["fuente"] for item in report["candidatas"]}
    assert urls["http://192.168.10.50:8080/?action=stream"].endswith("/app.js")
    assert report["webcams_publicadas"] == 0
    assert report["puertos_mencionados"] == [web_port]
    assert (tmp_path / "camara_busqueda.json").exists()
    assert web_seen == ["/", "/app.js"]  # the image is not fetched, nothing else is guessed
    assert set(api_seen) == {"/server/webcams/list", "/server/info", "/machine/system_info", "/server/config"}
