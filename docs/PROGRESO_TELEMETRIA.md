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
| 0. Descubrimiento | En curso: parte sin impresora |
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

**Pendiente sin impresora:**
- Script de descubrimiento de solo lectura (`backend/scripts/moonraker_discovery.py`).
- Impresora simulada para probarlo (`backend/scripts/mock_moonraker.py`).
- Plantilla de `docs/moonraker_discovery/README.md` con los datos esperados, marcados como sin verificar.

**Pendiente con la impresora:** correr el script de descubrimiento y completar el README y el análisis
del incidente con lo que devuelva.

**Decisiones:**
- El script guarda primero la evidencia que se pierde (registro de comandos en memoria y logs que
  rotan) y después el resto.

## Pendiente con la impresora

Antes de cualquier prueba: VPN HotspotShield desconectada, sesión `wsl -- sleep infinity` abierta y
`curl.exe http://192.168.10.22:7125/printer/info` respondiendo.

1. Correr el script de descubrimiento (Fase 0).
