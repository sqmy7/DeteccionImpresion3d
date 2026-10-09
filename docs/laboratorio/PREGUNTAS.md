# Preguntas para el profesor

Lo que, después de medir con la Creality Hi real (2026-10-08), todavía no se puede responder con los datos
que tenemos. Cada una lleva por qué importa y qué se intentó.

## La impresora

1. **¿Cómo accedió a la cámara interna?** Moonraker no publica ninguna (`/server/webcams/list` vacío en la
   .22; la .21 estaba apagada al intentarlo) y no se probó ninguna URL adivinada ni se escanearon puertos.
   ¿Fue por la aplicación de Creality, por una dirección concreta (puerto, ruta, protocolo), por WebRTC o
   con alguna configuración que se activa en la impresora? Es la segunda cámara que haría falta para
   comparar contra la C922.
2. **¿Qué hace exactamente la secuencia de reanudación de Creality?** `RESUME` llama a
   `RESUME_EXTERNAL_PROCESS`, que usa comandos internos (`BOX_GO_TO_EXTRUDE_POS`, `RESUME_FLUSH`,
   `BOX_NOZZLE_CLEAN`, `BOX_TIGHTEN_UP_ENABLE`) cuyo código no es legible desde Moonraker. El error del
   25-09 (`Move out of range: 292.424 249.610 28.401`, con X máx. = 285) no coincide con ninguna posición
   fija de la configuración. ¿Existe documentación o el código de esos comandos? ¿Se conoce algún caso de
   reanudación con ese error en la Hi?
3. **¿Cuáles son las potencias reales de los calentadores?** La configuración no las expone. La ficha dice
   1000 W (cama, a 220 V) y 390 W de potencia total a 110 V; la boquilla, 50 W según un repuesto. ¿Qué
   voltaje usa la instalación del laboratorio y qué potencia da la cama con él? De esto depende la
   energía estimada.
4. **¿Por qué el reloj de la impresora vuelve a 2020 en cada arranque?** Sin NTP ni RTC, los logs, el
   historial y la consola quedan con fechas falsas. ¿Hay una forma soportada de sincronizarlo?
5. **¿Cómo calcula la pantalla el porcentaje y el tiempo restante?** `display_status.progress` (el de la
   pantalla) no coincide con `virtual_sdcard.progress` (fracción del archivo leída), y esta última no es
   lineal en el tiempo. Lo que sí funcionó en la impresión medida fue el total del laminador (en el
   nombre del archivo) menos `print_duration`: 1 min de error medio sobre 2 h 45 min. ¿Es lo que usa la
   pantalla? ¿Se sabe por qué una capa (z ≈ 93 mm) tardó 24 min a 25 mm/s?
6. **El filamento:** `print_stats.filament_used` dio 68.220 mm, que por densidad son 208,4 g contra los
   201,83 g del laminador (+3,1 %). ¿Esos ~6,6 g son la purga y el cebado del inicio, o la densidad real
   del PETG usado difiere de la nominal (1,27 g/cm³)? ¿Cómo se pesa mejor para validarlo (pesar el
   carrete antes y después)?
7. **La caja CFS (`box`):** cuando se conecte, ¿cómo se comportan sus tres sensores y las ranuras?
   Hoy marcan "sin filamento" siempre.

## El modelo y la detección

8. **¿Con qué criterio se valida el modelo con la cámara y las piezas reales?** Las métricas del entrenamiento
   salen de fotos de Roboflow Universe; todavía no hay detecciones de la cámara final (C922) con la Hi: los 32 cuadros del trabajo 44 son de una cámara genérica provisional, sin la pieza a la vista. ¿Qué tamaño de
   muestra etiquetada y qué métrica se consideran suficientes antes de dejar que el modelo pause una
   impresión real?
9. **¿Puede el puntaje combinado (modelo + telemetría) llegar a influir en las alertas?** Hoy solo se
   muestra; sus pesos (0,6 / 0,3 / 0,15) son iniciales, sin calibrar. ¿Qué evidencia haría falta para
   calibrarlos (¿cuántas fallas reales etiquetadas?), sabiendo que una causa sin rastro en los sensores
   (un atasco parcial, filamento húmedo) no puede detectarse con ellos?
10. **Política de la pausa automática:** ¿debe PrintWatch poder pausar por su cuenta, o solo avisar? Hoy
    pausa tras 3 capas seguidas de *spaghetti* con 15 s de gracia, y no hay forma de dejarlo solo en aviso
    salvo apagar la captura.
11. **Calibración de la cámara:** el modelo ignora la distorsión del lente de la cámara (la C922 final o la genérica de prueba) (puede sumar varios
    milímetros en las esquinas). ¿Se justifica un patrón de calibración (tablero de ajedrez) o basta con
    el error estimado que ya se muestra?

## El método

12. **Salud de la impresora:** las cartas de control comparan cada trabajo con los primeros 5 a 10 de la
    misma impresora a igual temperatura. ¿Es aceptable que "normal" sea lo que la impresora hizo antes,
    aun si ya venía degradada, o se necesita una referencia externa?
