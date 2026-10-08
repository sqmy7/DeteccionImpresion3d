"""Finds the camera URLs a printer's own web interface uses, reading only what the printer serves.

Read-only and deliberately narrow:
  - only GET, only to the printer's own host;
  - only the pages the printer announces: Moonraker's webcam list and system info, and the web
    interface at the host's port 80 (plus any other port Moonraker's answers mention): its HTML and the
    scripts, styles and manifests that HTML loads, searched for camera addresses;
  - no port scans, no guessed paths, no credentials: a 401/403 stops the run;
  - few requests (--max-files), a download speed limit (--throttle-kb-s) and a cap per file.

With --probe URL it makes one GET to a URL found this way and keeps at most one frame (or 5 s).

usage (repo root):
    backend\\.venv\\Scripts\\python.exe backend\\scripts\\find_camera_urls.py --host 192.168.10.21 \\
        --out docs\\laboratorio\\impresora_21
"""

import argparse
import asyncio
import json
import posixpath
import re
import sys
import time
from pathlib import Path
from urllib.parse import urljoin, urlsplit

import httpx

MOONRAKER_PORT = 7125
_MAX_FILE_BYTES = 4 * 1024 * 1024
_SCAN_EXTENSIONS = {".js", ".html", ".htm", ".json", ".webmanifest", ".css", ""}

# Words that mark an address as a camera one.
_KEYWORDS = ("action=stream", "action=snapshot", "mjpg", "mjpeg", "webrtc", "whep", "webcam", "camera", ".m3u8", "rtsp://", "/stream", "snapshot")
_URL = re.compile(r"""(?:https?|rtsp|ws)://[^\s"'`<>()\\]+|(?<=["'`])/[A-Za-z0-9_\-./?=&%:]{3,200}(?=["'`])""")
_ASSET = re.compile(r"""(?:src|href)\s*=\s*["']([^"'#]+)["']""", re.IGNORECASE)
_JS_IMPORT = re.compile(r"""["'](\./[A-Za-z0-9_\-./]+\.(?:js|json))["']""")


class AuthenticationRequired(Exception):
    pass


def camera_candidates(text: str) -> list[str]:
    """Addresses in a page or script that look like camera ones (deduplicated, in order)."""
    found: list[str] = []
    for match in _URL.findall(text):
        cleaned = match.rstrip(",;.}]")
        lowered = cleaned.lower()
        if any(keyword in lowered for keyword in _KEYWORDS) and cleaned not in found:
            found.append(cleaned)
    return found


def linked_assets(html: str, base: str, host: str) -> list[str]:
    """Same-host files a page loads (scripts, styles, manifests), as absolute URLs."""
    assets: list[str] = []
    for reference in _ASSET.findall(html):
        url = urljoin(base, reference)
        parts = urlsplit(url)
        extension = posixpath.splitext(parts.path.lower())[1]  # "" for a path like /app
        if parts.hostname == host and parts.scheme in ("http", "https") and extension in _SCAN_EXTENSIONS and url not in assets:
            assets.append(url)
    return assets


def ports_mentioned(texts: list[str], host: str) -> list[int]:
    """Ports of http(s) URLs on the printer's own host that its answers mention."""
    ports: list[int] = []
    for text in texts:
        for match in re.findall(r"https?://([A-Za-z0-9_.\-]+):(\d{2,5})", text):
            if match[0] in (host, "localhost", "127.0.0.1") and int(match[1]) not in ports:
                ports.append(int(match[1]))
    return ports


class Reader:
    def __init__(self, host: str, throttle_kb_s: float | None, timeout: float = 10.0) -> None:
        self.host = host
        self.throttle = throttle_kb_s
        self.client = httpx.AsyncClient(timeout=timeout, follow_redirects=False)
        self.requests: list[dict] = []

    async def close(self) -> None:
        await self.client.aclose()

    async def get(self, url: str, *, max_bytes: int = _MAX_FILE_BYTES, max_seconds: float | None = None, binary: bool = False):
        parts = urlsplit(url)
        if parts.hostname != self.host:
            raise ValueError(f"Solo se consulta {self.host}, no {parts.hostname}")
        entry: dict = {"url": url, "utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
        started = time.monotonic()
        body = bytearray()
        try:
            async with self.client.stream("GET", url) as response:
                entry["status"] = response.status_code
                entry["content_type"] = response.headers.get("content-type")
                if response.status_code in (401, 403):
                    raise AuthenticationRequired(url)
                if response.status_code == 200:
                    async for chunk in response.aiter_bytes():
                        body.extend(chunk)
                        if self.throttle:
                            await asyncio.sleep(len(chunk) / (self.throttle * 1024))
                        if len(body) >= max_bytes or (max_seconds and time.monotonic() - started >= max_seconds):
                            entry["cortado"] = True
                            break
        except httpx.HTTPError as error:
            entry["error"] = f"{type(error).__name__}: {error}"
        entry["bytes"] = len(body)
        self.requests.append(entry)
        return entry, bytes(body)


async def find(host: str, out: Path, throttle: float | None, max_files: int) -> dict:
    reader = Reader(host, throttle)
    report: dict = {"host": host, "fuentes": [], "candidatas": [], "archivos_revisados": [], "puertos_mencionados": []}
    base_api = f"http://{host}:{MOONRAKER_PORT}"
    texts: list[str] = []
    try:
        for name, path in (("webcams", "/server/webcams/list"), ("server_info", "/server/info"), ("system_info", "/machine/system_info"), ("moonraker_config", "/server/config")):
            entry, body = await reader.get(base_api + path)
            text = body.decode("utf-8", "replace")
            texts.append(text)
            found = camera_candidates(text)
            report["fuentes"].append({"fuente": name, "estado": entry.get("status") or entry.get("error"), "candidatas": found})
            for url in found:
                report["candidatas"].append({"url": url, "fuente": f"Moonraker {path}"})
            if name == "webcams" and entry.get("status") == 200:
                try:
                    report["webcams_publicadas"] = len(json.loads(text)["result"]["webcams"])
                except (KeyError, ValueError):
                    pass

        report["puertos_mencionados"] = ports_mentioned(texts, host)
        origins = [f"http://{host}"] + [f"http://{host}:{port}" for port in report["puertos_mencionados"] if port != MOONRAKER_PORT]
        budget = max_files
        for origin in origins:
            entry, body = await reader.get(origin + "/", max_bytes=1024 * 1024)
            report["fuentes"].append({"fuente": f"interfaz web {origin}", "estado": entry.get("status") or entry.get("error")})
            if entry.get("status") != 200:
                continue
            html = body.decode("utf-8", "replace")
            for url in camera_candidates(html):
                report["candidatas"].append({"url": url, "fuente": f"HTML de {origin}/"})
            queue = linked_assets(html, origin + "/", host)
            seen = set(queue)
            while queue and budget > 0:
                url = queue.pop(0)
                budget -= 1
                entry, body = await reader.get(url)
                report["archivos_revisados"].append({"url": url, "estado": entry.get("status") or entry.get("error"), "bytes": entry.get("bytes")})
                if entry.get("status") != 200:
                    continue
                text = body.decode("utf-8", "replace")
                for candidate in camera_candidates(text):
                    report["candidatas"].append({"url": candidate, "fuente": url})
                # Chunks a bundler loads lazily are named in the entry scripts.
                for reference in _JS_IMPORT.findall(text):
                    nested = urljoin(url, reference)
                    if urlsplit(nested).hostname == host and nested not in seen:
                        seen.add(nested)
                        queue.append(nested)
            report["archivos_sin_revisar"] = len(queue)
    except AuthenticationRequired as error:
        report["detenido_por_autenticacion"] = str(error)
    finally:
        report["peticiones"] = reader.requests
        await reader.close()
    out.mkdir(parents=True, exist_ok=True)
    (out / "camara_busqueda.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    return report


async def probe(host: str, url: str, out: Path) -> dict:
    """One GET to a camera URL: at most one frame (or 5 s) is read and one JPEG kept."""
    reader = Reader(host, None, timeout=8.0)
    try:
        entry, body = await reader.get(url, max_bytes=2 * 1024 * 1024, max_seconds=5)
    finally:
        await reader.close()
    result = {"url": url, "estado": entry.get("status") or entry.get("error"), "content_type": entry.get("content_type"), "bytes_leidos": entry.get("bytes")}
    start = body.find(b"\xff\xd8\xff")
    end = body.find(b"\xff\xd9", start + 3) if start != -1 else -1
    if start != -1 and end != -1:
        out.mkdir(parents=True, exist_ok=True)
        (out / "camara_cuadro.jpg").write_bytes(body[start : end + 2])
        result["cuadro_guardado"] = True
        result["cuadro_bytes"] = end + 2 - start
    else:
        result["cuadro_guardado"] = False
    (out / "camara_prueba.json").write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Busca las URL de cámara que publica la propia impresora (solo lectura).")
    parser.add_argument("--host", required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--throttle-kb-s", type=float, default=300.0)
    parser.add_argument("--max-files", type=int, default=30)
    parser.add_argument("--probe", help="una URL hallada: un GET, un cuadro como máximo")
    args = parser.parse_args()
    if args.probe:
        result = asyncio.run(probe(args.host, args.probe, args.out))
    else:
        result = asyncio.run(find(args.host, args.out, args.throttle_kb_s, args.max_files))
        result = {key: value for key, value in result.items() if key != "peticiones"}
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
