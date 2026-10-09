# Hallazgos de la Etapa C: recorrido en el navegador (2026-10-09)

Recorrido con Playwright (Edge, 1440×900) contra la **demostración**: impresora **simulada** (con la pausa tardando
3 s y la reanudación 8 s, como la real tarda ~9 s y 45 a 65 s), base de demostración y token de 29 minutos. No se tocó
ninguna impresora real ni la base real. `resultado.json` trae las comprobaciones (todas verdaderas) y los errores de
consola (solo los 401 provocados a propósito, que se esperan).

| Comprobación | Resultado |
|---|---|
| El token se renueva al abrir la web (una llamada a `/auth/refresh` con 200) y la pantalla no se recarga | sí |
| «Pausar impresión» → la impresora pasa a pausada y el botón vuelve a «Reanudar impresión» | sí |
| «Reanudar impresión» muestra «Reanudando… N s» hasta que la impresora vuelve a imprimir; sin textos de error ni 502 | sí |
| Un 401 al pulsar «Pausar» lleva al login con «Tu sesión caducó. Inicia sesión de nuevo.», borra el token y no pausa nada | sí |
| Usuario o clave mal puestos siguen diciendo «Usuario o contraseña incorrectos.» (sin el aviso de sesión caducada) | sí |
| Abrir la web con un token guardado ya inválido lleva al login con el aviso; volver a entrar funciona | sí |

Capturas: `1_pausada.png`, `2_reanudada.png` y `3_sesion_caducada.png`.
Lo que **no** muestra: la impresora real (la Creality Hi no se ha probado con estos cambios).
