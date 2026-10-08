# Segunda impresora (192.168.10.21): no se pudo explorar

**No respondió en toda la sesión** (15:00 a 17:08, hora de Colombia). Por eso no hay descubrimiento, ni
cámara, ni comparación contra la .22: no se inventó ninguna fila.

## Qué se comprobó

| Intento | Resultado |
|---|---|
| `GET http://192.168.10.21:7125/printer/info` (5 s, 15 s, y de nuevo cada ~5 min con un monitor) | sin respuesta (HTTP 000) |
| `ping` único a 192.168.10.21 (2 paquetes) | 100 % perdidos |
| Entrada ARP de 192.168.10.21 | no existe: el equipo no está contestando en esa red |
| Mismo momento, `GET http://192.168.10.22:7125/printer/info` | responde (la .22 y la red estaban bien) |
| Red | SalaSteam_UIS, sin VPN |

La causa más probable es que esté apagada o tenga otra dirección (el DHCP del laboratorio puede haberla
cambiado). No se intentó nada más: ni escaneo de la red, ni adivinar la IP.

## Qué quedó listo para cuando responda

- `backend/scripts/moonraker_discovery.py` ya acepta `--url`, `--throttle-kb-s`, `--steps`,
  `--skip-webcam-stream` y `--ws-skip-macros`:

  ```powershell
  # .21 quieta (standby): corrida completa, WebSocket 60 s
  backend\.venv\Scripts\python.exe backend\scripts\moonraker_discovery.py --url http://192.168.10.21:7125 `
      --out docs\laboratorio\impresora_21\descubrimiento --throttle-kb-s 300 --ws-seconds 60
  ```

- `backend/scripts/find_camera_urls.py` (nuevo, con pruebas) busca la cámara solo con lo que la impresora
  publica: `/server/webcams/list`, `/server/info`, `/machine/system_info`, `/server/config` y la interfaz
  web del puerto 80 con sus scripts. Sin escaneo de puertos, sin rutas adivinadas, se detiene ante 401/403;
  `--probe URL` hace un solo GET a una URL hallada y guarda un cuadro:

  ```powershell
  backend\.venv\Scripts\python.exe backend\scripts\find_camera_urls.py --host 192.168.10.21 --out docs\laboratorio\impresora_21
  ```

- Antes de correrlos: confirmar con `curl.exe -m 5 http://192.168.10.21:7125/printer/info` y que
  `print_stats.state` sea `standby`.

## Análisis de las macros para el incidente (con las de la .22; no se probó nada)

Las macros de la .21 no se pudieron leer; estas son las de la .22 (`docs/laboratorio/descubrimiento/macros.cfg`,
mismo firmware `09faed31-dirty`). Se busca qué cálculo da X = 292,424 (límite 285), Y = 249,610 y Z = 28,401:

- **Ninguna posición fija coincide:** extrusión (X −18,5, Y 130), corte (279,6, 130), pre-corte (240, 130),
  estacionamiento de pausa (`axis_maximum.x − 10` = 275, `axis_maximum.y / 2` = 136,5), fin de impresión (0, 260),
  cancelación (10, 260), final del archivo (0, 180).
- **`PAUSE_EXTERNAL`** sube la Z hasta 50 si estaba por debajo de 48 (coincide con `z_pos = 49,929` del
  incidente) y guarda `z_safe_pause`; **`RESUME_EXTERNAL`** vuelve a bajar `z_safe_pause − 2` con `G91` y
  **no restablece `G90` al terminar**; después llama a `BOX_GO_TO_EXTRUDE_POS`, `RESUME_FLUSH` y
  `BOX_NOZZLE_CLEAN` (comandos internos de Creality) y la macro `RESUME` termina con `RESUME_BASE`, que en Klipper
  restaura el estado guardado al pausar (incluido el modo de coordenadas) y vuelve a la posición de la pausa.
- **Hipótesis (no demostrada):** si algo impidió el restablecimiento (un error en medio de la secuencia) y quedó
  `G91` activo, las líneas absolutas del archivo se habrían sumado a la posición. Como ilustración aritmética: las
  últimas líneas del archivo del incidente tienen `Z25.4` y 28,401 − 25,4 = **3,001 mm**; no hay ninguna
  evidencia de que la cabeza estuviera a esa Z, así que es solo una coincidencia numérica a descartar con los logs
  de la .21 o con una prueba controlada, que no se hace sin tu orden.
- Con lo anterior, **no se puede afirmar qué cálculo produjo 292,424**. La guardia contra reanudaciones
  duplicadas (`print_guard.py`) cubre el caso de la orden repetida, pero no esta hipótesis.

## Qué necesito de ti

1. Encender la .21 (o decirme su IP actual) y avisarme: el descubrimiento y la búsqueda de cámara están listos.
2. Si el profesor puede decir cómo accedió a la cámara interna (URL y protocolo), con eso basta para una sola
   prueba con `--probe`.
