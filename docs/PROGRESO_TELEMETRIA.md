# Progreso: telemetría, bitácora, mapa de la cama y rediseño

Archivo de seguimiento del trabajo de telemetría. Si la sesión se corta, al retomar se lee este archivo
y `git log` antes de tocar nada.

**Regla de seguridad (no negociable):** todo el trabajo es de solo lectura sobre la impresora. No se
envía G-code ni órdenes que muevan motores, cambien temperaturas, hagan home, pausen, reanuden o
cancelen, tampoco en pruebas o calibración. La única orden que el sistema envía por su cuenta es la
pausa automática por spaghetti, que no se modifica. Lo que necesite órdenes se prueba contra la
impresora simulada (`backend/scripts/mock_moonraker.py`).

**Contexto de esta tanda:** se trabaja sin acceso a la impresora (fuera de la red del laboratorio).
Lo que necesita la impresora real queda preparado para correrlo después y anotado en
"Pendiente con la impresora".

## Estado por fase

| Fase | Estado |
|---|---|
| 0. Descubrimiento | Parte sin impresora terminada; falta correr el script en el laboratorio |
| 1. Telemetría con fecha y hora | Sin empezar |
| 2. Bitácora de intervenciones | Sin empezar |
| 3. Mapa de la cama | Sin empezar |
| 4. Rediseño de la web | Sin empezar |
| 5. Innovación | Sin empezar |

## Fase 0: descubrimiento

**Hecho:**
- Punto de restauración antes de empezar: commit `1deb2e4`.
- Análisis del incidente de reanudación del 25-09-2026 con la evidencia disponible sin la impresora
  (base de datos y respuestas de Moonraker registradas): `docs/moonraker_discovery/incidente_reanudacion.md`.
- Script de descubrimiento de solo lectura: `backend/scripts/moonraker_discovery.py`. Guarda consola,
  logs (con extractos del incidente), historial, objetos y su estado, configuración y macros, inicio y
  final de los G-code, cámara interna (imagen y cuadros por segundo), equipo y una medición del
  WebSocket por campo. Modo `--only-ws` para medir durante una impresión sin descargar nada.
- Impresora simulada: `backend/scripts/mock_moonraker.py`. Simula una impresión (cabezal, capas,
  temperaturas, objetos, malla), la consola de G-code (para simular intervenciones externas), las
  órdenes de pausa/reanudación/cancelación, un error como el del incidente y una cámara MJPEG cuya
  imagen proyecta la cama con una homografía conocida (servirá para probar la calibración de la Fase 3).
- Pruebas automáticas (`backend/tests/`, 16 pruebas): lista blanca de solo lectura, extracción del
  incidente en los logs y corrida del descubrimiento contra la simulada dentro del proceso.
- Plantilla `docs/moonraker_discovery/README.md` con la tabla de datos esperados, marcados como
  *sin verificar* salvo lo ya medido.
- Fuentes de cámara de red en `capture/` (antes eran stubs): MJPEG por HTTP y RTSP con el backend
  FFmpeg de OpenCV y timeout de 5 s. Probado contra el stream de la simulada.

**Pendiente con la impresora:** correr el script (corrida completa con la impresora sin imprimir y
`--only-ws` durante una impresión), completar el README y el análisis del incidente, y si la cámara
interna da imagen por MJPEG o RTSP, agregarla como cámara `secondary` de la impresora 35 y compararla
con la C922.

**Decisiones:**
- El script guarda primero la evidencia que se pierde (consola en memoria y logs que rotan).
- Si la impresora pide credenciales, el script se detiene y no intenta ninguna (regla del proyecto).
- Los logs completos no se versionan (pesan y traen datos del equipo); sí los extractos. De
  `system_info` se ocultan números de serie y direcciones MAC.
- Las URLs de cámara relativas se prueban primero en los puertos web (80 y 4408, donde las resuelve
  Fluidd) y luego en el de Moonraker; nunca se prueban URLs de otros equipos ni rutas de la API.
- La cámara interna, si se agrega, va como `secondary`: los archivos de captura se nombran por rol, así
  que dos cámaras `primary` en la misma impresora se pisarían.

## Pendiente con la impresora

Antes de cualquier prueba: VPN HotspotShield desconectada, sesión `wsl -- sleep infinity` abierta y
`curl.exe http://192.168.10.22:7125/printer/info` respondiendo.

1. Fase 0: `backend\.venv\Scripts\python.exe backend\scripts\moonraker_discovery.py` con la impresora
   sin imprimir, y `... --only-ws --ws-seconds 600` durante una impresión.
