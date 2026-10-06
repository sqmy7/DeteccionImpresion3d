import argparse
import getpass
import json
import os
import sys
from decimal import Decimal, InvalidOperation

import httpx
import redis


class Api:
    def __init__(self, base_url: str, username: str, password: str) -> None:
        self._client = httpx.Client(base_url=base_url, timeout=10)
        self._username = username
        self._password = password
        self._token = ""

    def login(self) -> None:
        response = self._client.post(
            "/api/v1/auth/login", data={"username": self._username, "password": self._password}
        )
        response.raise_for_status()
        self._token = response.json()["access_token"]

    def request(self, method: str, path: str, **kwargs) -> httpx.Response:
        response = self._send(method, path, **kwargs)
        if response.status_code == 401:
            self.login()
            response = self._send(method, path, **kwargs)
        response.raise_for_status()
        return response

    def _send(self, method: str, path: str, **kwargs) -> httpx.Response:
        return self._client.request(method, path, headers={"Authorization": f"Bearer {self._token}"}, **kwargs)


def describe_error(error: httpx.HTTPError) -> str:
    if isinstance(error, httpx.HTTPStatusError):
        try:
            return f"{error.response.status_code}: {error.response.json().get('detail')}"
        except ValueError:
            return str(error.response.status_code)
    return str(error)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Marca cambios de capa a mano y dispara la captura.")
    parser.add_argument("--printer-id", type=int, required=True)
    parser.add_argument("--file-name", help="nombre de la impresión (solo si se crea un job nuevo)")
    parser.add_argument("--layer-height", type=float, default=0.2, help="altura de capa en mm")
    parser.add_argument("--first-layer-height", type=float, help="por defecto igual a --layer-height")
    parser.add_argument("--step", type=int, default=1, help="cuántas capas avanza cada Enter")
    parser.add_argument("--api-url", default=os.environ.get("PRINTWATCH_API_URL", "http://localhost:8000"))
    parser.add_argument("--redis-url", default=os.environ.get("PRINTWATCH_REDIS_URL", "redis://localhost:6379/0"))
    args = parser.parse_args()

    if args.step < 1:
        parser.error("--step debe ser >= 1")
    if args.first_layer_height is None:
        args.first_layer_height = args.layer_height
    return args


def resolve_job(api: Api, printer_id: int, file_name: str | None) -> dict:
    jobs = api.request("GET", f"/api/v1/printers/{printer_id}/print-jobs").json()
    running = next((job for job in jobs if job["status"] == "running"), None)

    if running is not None:
        print(f"Ya hay un job en curso: #{running['id']} '{running['file_name']}' (inicio {running['started_at']})")
        choice = input("[c] continuar ese job / [n] cancelarlo y empezar uno nuevo / [q] salir > ").strip().lower()
        if choice == "c":
            return running
        if choice != "n":
            sys.exit(0)
        api.request("POST", f"/api/v1/print-jobs/{running['id']}/transition", json={"status": "cancelled"})

    name = file_name or input("Nombre de la impresión [impresion_manual] > ").strip() or "impresion_manual"
    return api.request("POST", f"/api/v1/printers/{printer_id}/print-jobs", json={"file_name": name}).json()


def last_layer_number(api: Api, job_id: int) -> int:
    layers = api.request("GET", f"/api/v1/print-jobs/{job_id}/layers").json()
    return max((layer["layer_number"] for layer in layers), default=0)


def z_for(number: int, first_layer_height: float, layer_height: float) -> Decimal:
    z = Decimal(str(first_layer_height)) + (number - 1) * Decimal(str(layer_height))
    return z.quantize(Decimal("0.01"))


def parse_layer_input(line: str, default_number: int) -> tuple[int, Decimal | None]:
    parts = line.split()
    number = int(parts[0]) if parts else default_number
    if number < 1:
        raise ValueError("layer number must be >= 1")
    z = Decimal(parts[1]) if len(parts) > 1 else None
    return number, z


def trigger_capture(redis_client: redis.Redis, printer_id: int, payload: dict) -> None:
    try:
        listeners = redis_client.publish(f"layer_ready:{printer_id}", json.dumps(payload))
    except redis.RedisError as error:
        print(f"No se pudo publicar en Redis: {error}. La capa quedó registrada; usá 'r' para reintentar.")
        return

    if listeners == 0:
        print("ATENCIÓN: nadie escucha layer_ready (¿está corriendo capture?). Arrancalo y usá 'r' para reintentar.")
    else:
        print(f"Capa {payload['layer_number']} (z={payload['z_height']}) registrada, captura disparada.")


def close_job(api: Api, job_id: int, new_status: str) -> bool:
    label = "COMPLETADO" if new_status == "completed" else "FALLIDO"
    if input(f"¿Cerrar el job #{job_id} como {label}? [s/N] > ").strip().lower() != "s":
        return False

    try:
        api.request("POST", f"/api/v1/print-jobs/{job_id}/transition", json={"status": new_status})
    except httpx.HTTPError as error:
        print(f"No se pudo cerrar el job: {describe_error(error)}")
        return False

    print(f"Job #{job_id} marcado como {new_status}.")
    return True


def mark_loop(api: Api, redis_client: redis.Redis, printer_id: int, job: dict, args: argparse.Namespace) -> None:
    job_id = job["id"]
    last_number = last_layer_number(api, job_id)
    last_payload: dict | None = None

    print(f"Impresora #{printer_id} | job #{job_id} | última capa registrada: {last_number}")
    print("Enter = capa siguiente | <n> [z] = capa n | r = reenviar la última | f = terminar OK | x = terminar fallida | q = salir")

    while True:
        default_number = last_number + args.step
        line = input(f"capa #{default_number} > ").strip().lower()

        if line == "q":
            print(f"Saliendo. El job #{job_id} sigue en curso.")
            return
        if line in ("f", "x"):
            if close_job(api, job_id, "completed" if line == "f" else "failed"):
                return
            continue
        if line == "r":
            if last_payload is None:
                print("Todavía no marcaste ninguna capa en esta sesión.")
            else:
                trigger_capture(redis_client, printer_id, last_payload)
            continue

        try:
            number, z = parse_layer_input(line, default_number)
        except (ValueError, InvalidOperation):
            print("Entrada no válida: Enter, un número de capa >= 1 (con z opcional), o q/f/x/r.")
            continue
        if z is None:
            z = z_for(number, args.first_layer_height, args.layer_height)

        try:
            api.request("POST", f"/api/v1/print-jobs/{job_id}/layers", json={"layer_number": number, "z_height": str(z)})
        except httpx.HTTPError as error:
            print(f"No se pudo registrar la capa {number}: {describe_error(error)}")
            continue

        last_number = number
        last_payload = {"printer_id": printer_id, "job_id": job_id, "layer_number": number, "z_height": str(z)}
        trigger_capture(redis_client, printer_id, last_payload)


def main() -> None:
    args = parse_args()
    username = os.environ.get("PRINTWATCH_USER") or input("Usuario admin > ").strip()
    password = os.environ.get("PRINTWATCH_PASSWORD") or getpass.getpass("Contraseña > ")

    api = Api(args.api_url, username, password)
    try:
        api.login()
        job = resolve_job(api, args.printer_id, args.file_name)
    except httpx.HTTPError as error:
        sys.exit(f"Error hablando con el backend ({args.api_url}): {describe_error(error)}")

    redis_client = redis.Redis.from_url(args.redis_url, decode_responses=True)
    try:
        redis_client.ping()
    except redis.RedisError as error:
        sys.exit(f"No se pudo conectar a Redis ({args.redis_url}): {error}")

    try:
        mark_loop(api, redis_client, args.printer_id, job, args)
    except (KeyboardInterrupt, EOFError):
        print(f"\nSaliendo. El job #{job['id']} sigue en curso; volvé a correr el script para continuar.")


if __name__ == "__main__":
    main()
