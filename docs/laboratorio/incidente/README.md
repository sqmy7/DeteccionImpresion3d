# Incidentes: recorrido con la demostración (2026-10-09)

Capturas y resultados de recorrer la pantalla de «Incidente» en un navegador real (Edge, escritorio 1440×900 y
celular 390×844) contra la **demostración**: impresora **simulada** y base de demostración (`printwatch_demo`).
No se tocó ninguna impresora ni la base real. Se generó con `backend/scripts/demo_environment.py --incident
--auto-pause-mode warn|on` (spaghetti sintético en tres capas seguidas) y un recorrido con Playwright.

| Archivo | Qué muestra |
|---|---|
| `warn_*_1_panel_con_aviso.png` | El aviso fijo en una pantalla sin relación (Panel general); modo aviso |
| `warn_*_2_lista.png`, `warn_*_3_detalle.png` | La lista y el detalle del incidente en modo aviso (se habría pausado, la impresora sigue imprimiendo) |
| `warn_desktop_4_cancelar_dialogo.png`, `warn_desktop_5_cancelada.png` | La doble confirmación de cancelar (escribir `CANCELAR`) y el incidente cerrado como «Se canceló» por el usuario |
| `on_desktop_0_cuenta_regresiva.png` | Modo automático durante la cuenta regresiva: aparece «Abortar la pausa» |
| `on_*_1`, `on_*_2`, `on_*_3` | Panel con aviso, lista y detalle con la impresora pausada y confirmada |
| `on_desktop_4_pausada_antes_de_reanudar.png`, `on_desktop_5_reanudada.png` | Reanudar desde la pantalla (con la guarda) y el incidente cerrado como «Se reanudó» |
| `resultado_warn.json`, `resultado_on.json` | Las comprobaciones automáticas del recorrido (todas verdaderas) y los errores de consola |

Comprobado en ambos modos: sin errores de consola; sin desplazamiento horizontal en celular; foto de la capa con
sus cajas y la galería de la racha; clase, confianza, capa y hora; estado de la impresora (temperaturas y
objetivos, velocidad y factor, flujo, ventilador, posición, sensores de filamento, progreso, tiempo impreso y
restante) al aviso y al pausarse; línea de tiempo con el origen de cada evento y la cadena íntegra; el aviso
fijo con la marca `(!)` en el título de la pestaña; etiquetar acierto o falso positivo; reanudar y cancelar.

Lo que **no** muestra: una impresora real ni un modelo real (las detecciones de la demostración son sintéticas), y
la cámara de la demostración no es la C922.
