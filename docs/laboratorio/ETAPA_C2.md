# Etapa C2: pausa y reanudación reales con los arreglos de los hallazgos (2026-10-09)

Impresora 35 «Creality Hi-3422» (192.168.10.22). Backend desplegado el 2026-10-09 con los arreglos de los hallazgos 1 a 4 de la Etapa C (`b4e7904`, `3451c3b`,
`d425820`, `76e58f2`, `38e12ad`). `AUTO_PAUSE_MODE=warn` todo el tiempo. **PrintWatch no mandó ninguna orden a la impresora por su cuenta**: la pieza la inició Samuel desde
la pantalla de la impresora y las dos pausas y las dos reanudaciones las pulsó él en la web. Observación solo con lecturas (`GET` cada segundo a Moonraker, `SELECT`, el log
del backend y la edad del video en Redis). `capture` corría en una terminal de Samuel durante toda la prueba. Horas locales.

Pieza: **`Cubo_PLA_12m58s.gcode`** (86 capas, PLA, boquilla a 220 °C), trabajo 47, 19:18:30 a 19:36:54, `completed`. No es la `Cubo_PETG_18m27s` que se había supuesto: dura menos y
la preparación fue de unos 8 min (19:10:10 a 19:18:29), no 11.

## Sesión web

| Hora | Llamada |
|---|---|
| 18:03:07 | `POST /auth/login` → 200 (inicio de sesión de Samuel) |
| 18:36:24 | `POST /auth/refresh` → **200** (primera renovación, 33 min después del login) |
| 19:07:20 | `POST /auth/refresh` → **200** (segunda, 31 min después) |

Antes de pausar ya constaban las dos renovaciones. Durante la prueba no hubo ningún 401, 409, 502 ni 500 en el log del backend.

## Pausas y reanudaciones (medido)

| | Pausa 1 | Reanudación 1 | Pausa 2 | Reanudación 2 |
|---|---|---|---|---|
| Orden de la web («Manual … requested») | 19:22:00,306 | 19:23:07,679 | 19:25:15,966 | 19:26:33,581 |
| Orden en la bitácora (`printwatch_command`, «samuel (web)», `ok` vacío = enviada) | 19:22:00,867 | 19:23:07,815 | 19:25:16,069 | 19:26:33,779 |
| Cambio de estado en la bitácora (origen `printwatch`) | 19:22:01,438 `paused` | 19:24:13,116 `printing` | 19:25:16,904 `paused` | 19:27:37,673 `printing` |
| Del clic al cambio de estado | **1,0 s** (listener a las 19:22:01,330) | **65,4 s** | **0,84 s** | **64,1 s** |
| Respuesta de la web | 202 a las 19:22:03,874 (3,6 s) | 202 a las 19:23:10,817 (3,1 s) | 202 a las 19:25:19,071 (3,1 s) | 202 a las 19:26:36,781 (3,2 s) |
| Capa | 18 de 86 | vuelve en la 18 | 26 de 86 | vuelve en la 26 |
| Posición al pausar | X 136,1 / Y 131,5 / Z 3,7 | | X 136,1 / Y 122,3 / Z 5,1 | |

**Pausa (las dos iguales):** tras el cambio de estado la cabeza sigue moviéndose: sube a Z 50 a los ~8 s y llega al estacionamiento **X 0 / Y 260 / Z 50** a los ~20 s (19:22:22 y
19:25:36). El objetivo de la boquilla baja de 220 a 140 °C a los 12 a 14 s (19:22:14 y 19:25:30); la boquilla estaba a 164,6 °C a los 60 s en la pausa 1; la cama se mantuvo en
59,4 a 60,1 °C con objetivo 60.

**Reanudación (las dos iguales):** el objetivo de la boquilla vuelve a 220 °C al instante, llega a ≥ 215 °C a los ~20 s (19:23:28 y 19:26:56), la cabeza baja de Z 50 a Z 6,2 y va a
X −18,5 / Y 130 (a **0,5 mm del límite −19**, igual que en la Etapa C, sin error), y el estado vuelve a `printing` a los ~65 s. Rango recorrido en la reanudación 2: X −18,5 a 137,4,
Y 130 a 260 (límites X −19..285, Y −7..273). **Ningún error de Klipper ni `resume_err`** en toda la prueba. La orden de reanudar no figura como fallida (sin `ReadTimeout`).

## Incidentes y bitácora

- Incidentes 3 y 7 (`would_pause`, modo `warn`, clase `spaghetti`): abiertos a las 19:20:10 y 19:24:58 por la detección; las pausas de Samuel los marcaron `paused` (19:22:01 y 19:25:16) y las
  reanudaciones los cerraron como `resumed` por «samuel (web)» (19:24:13 y 19:27:37). `pause_sent_at` vacío: PrintWatch no mandó ninguna pausa (modo `warn`).
- Cadena de la bitácora de la impresora 35: **íntegra, 340 eventos**. Las órdenes y los cambios de estado aparecen en ese orden y atribuidos a `printwatch` (el hallazgo 4 ya no se da).

## Capturas y video (con `capture` corriendo)

- **86 capas y 86 capturas, ninguna sin captura.** Retraso de la captura respecto a la capa: mínimo 0,4 s, medio 0,7 s, máximo 1,8 s. Tabla completa en
  [etapa_c2/capturas_trabajo_47.txt](etapa_c2/capturas_trabajo_47.txt) (consultas en [c2_capturas.sql](c2_capturas.sql)).
- **Huecos:** los de las pausas: capa 18 → 19, **140,4 s**, y capa 26 → 27, **149,9 s**; otros dos de 13,7 y 13,8 s (capa 2 y capa 83) sin relación con las pausas.
  **0 capturas durante cada pausa**, como se esperaba (se capturan por capa).
- **Primera captura tras reanudar:** capa 19 a las 19:24:15, **2,3 s** después de volver a `printing`; capa 27 a las 19:27:44, **6,6 s** después.
- **Video en vivo (Redis):** edad máxima **0,76 s** en 1 145 muestras (desde las 19:18:30), ninguna mayor de 2 s: no se cortó en la pausa ni en la reanudación.
- 1 068 muestras de telemetría en la base.

## Detecciones (modo `warn`, no actuó nada)

20 detecciones de `spaghetti` (confianza 0,258 a 0,570) y 1 de `under_extrusion` (0,334) en 86 capas; el modelo avisó 3 veces de una racha de 3 capas seguidas (19:20:10 capa 6, 19:21:36 capa 16,
19:24:58 capa 24). **Se miró la foto de la capa 24 (la de mayor confianza, 0,570): no muestra la pieza en el encuadre**; la cámara ve la cama de lado con el cabezal a la izquierda y la pieza no se
ve, así que esa detección no puede corresponder a un spaghetti real. De las otras no se miró ninguna. No se declara la causa más allá de eso (la cámara es la genérica, no está en la posición de la
calibración y no ve la pieza); con `AUTO_PAUSE_MODE=on` estas detecciones habrían pausado la impresión.

## Qué se comprobó de los arreglos (con la impresora real)

| Hallazgo | Resultado |
|---|---|
| 1. Respuesta «aceptada» sin esperar a la impresora | **Comprobado**: 202 a los ~3 s en las 4 órdenes (no 502); la orden queda como enviada y no como fallida; la reanudación real tardó ~65 s |
| 4. Atribución de la pausa a `printwatch` | **Comprobado**: las dos pausas y las dos reanudaciones, `printwatch`, con la orden antes del cambio de estado |
| 3. Sesión | **Comprobado**: dos renovaciones con 200 antes de la prueba y ningún 401 durante ella |
| 2. Guarda de reanudación en curso | **No probado**: nadie pulsó un segundo clic mientras reanudaba |
| Pausa con lectura previa del estado (`38e12ad`) | Camino feliz usado en las dos pausas; el camino de impresora inalcanzable no se probó con la real |

**No medido:** lo que la web mostró en pantalla («Pausando…», «Reanudando… N s»); no se observó el navegador de Samuel.

## Qué sigue

1. Decidir `AUTO_PAUSE_MODE` a la vista de las detecciones falsas con esta cámara (y la pausa automática inducida, que necesita «autorizo la C»).
2. Cancelación real, solo con «autorizo cancelar».
3. Reposicionar la cámara para que vea la pieza y recalibrar con la C922 (y revisar el umbral de `spaghetti` antes de pasar a `on`).
4. Pendientes de la cámara: aviso de «captura detenida» en la web y un script que arranque `capture` comprobando antes la cámara.
