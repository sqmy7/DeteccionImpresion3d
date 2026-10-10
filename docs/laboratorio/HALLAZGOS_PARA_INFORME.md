# Hallazgos para el informe de laboratorio

Lista corta de lo que **cambió respecto de lo supuesto** y de **cada cifra medida** con la Creality Hi real
(2026-10-08), para actualizar el informe. Cada punto dice qué se suponía, qué se midió y dónde está el detalle.
Solo se midió con lecturas (GET, WebSocket de lectura y `SELECT`); a ninguna impresora se le envió una orden.

Dos trabajos sirvieron de base: el **43** (`CAJA LISTA CARA ADALOVE…_PETG_6h0m27s.gcode`, 486 capas, 6 h) y el
**44** (`Cubo_PETG_2m28s.gcode`, 32 capas, 3 min 36 s, seguido desde el inicio).

> **Sobre la cámara:** las pruebas del 8 de octubre se hicieron con una **cámara USB genérica provisional**, no con la
> Logitech C922, que será la cámara de la implementación final (aclaración de Samuel, 2026-10-09). Los puntos que
> dependen de la cámara lo dicen.

## La impresora

1. **El tamaño de la cama.** Se suponía el recorrido de los ejes; se midió que Klipper reporta X −19…285, Y −7…273,
   Z −5…310 (incluye el cortador de filamento, en X = 279,6), mientras la cama es de **260 × 260 mm** (la malla va
   de 10 a 250). Además, con la impresora quieta y sin malla cargada, Klipper reporta la malla como `[0, 0]` a
   `[0, 0]`: calculado desde ahí, el tamaño de la cama salía 0 y la calibración de la cámara fallaba (corregido: una
   malla vacía no cuenta y se usa 260). *Detalle:* `RESULTADOS.md` §2.1, `PROGRESO_FINAL.md`.
2. **La posición real del cabezal** es `motion_report.live_position` (~4 Hz, un mensaje cada 0,251 s).
   `toolhead.position` no sirve: va por delante del cabezal real **~100 mm de mediana (p90 162 mm)**, medido en 1.189
   pares.
3. **El reloj de la impresora** vuelve a **2020-01-01** en cada arranque (sin NTP ni RTC; diferencia de −213.636.671 s
   con el equipo), así que todas las horas se toman del equipo y no de la impresora.
4. **Los sensores de filamento son cinco**: el del cabezal, uno más y tres de la caja CFS. Los tres de la caja dicen
   siempre «sin filamento» (la caja no está conectada), aunque cambian de estado cuando se mueve filamento. Con la
   lógica anterior eso habría sumado +0,6 al puntaje de `under_extrusion` en todo trabajo; ahora solo cuenta un
   sensor que haya visto filamento durante el trabajo.
5. **No existe el objeto `fan`.** El ventilador de capa es `output_pin fan0` (y `fanp0`); `fan_speed` estaba vacío en
   todas las muestras. Leído de ahí, en el trabajo 44 el ventilador de capa trabajó al ~40 %.
6. **Los metadatos del laminador** no traen `estimated_time`, `filament_total` ni `filament_weight_total`: traen
   `layer_count` y `filament_used_g` (una lista de cadenas: `["201.83"]`, `["0.28", "0.00", …]`). El **tiempo
   estimado solo está en el nombre del archivo** (`…_6h0m27s`, `…_2m28s`). Los metadatos del archivo en
   `/server/files/metadata` son casi vacíos (laminador «Unknown»); los completos salen de
   `virtual_sdcard.cur_print_data.metadata` mientras el archivo está cargado.
7. **Moonraker no publica ninguna cámara** (`/server/webcams/list` vacío, también con la impresora quieta, y la
   configuración, las macros y los 117 objetos idénticos en ambos estados). No se probó ninguna URL adivinada. La
   segunda impresora (192.168.10.21) no respondió en ninguna de las pruebas.
8. **Las potencias de los calentadores** no están en la configuración: los supuestos de 50 W (boquilla) y 300 W
   (cama) **siguen sin verificarse**; por eso el costo de energía es una estimación (trabajo 43: 0,40 kWh con
   telemetría de la mitad final).
9. **Antes de imprimir, la Hi se prepara ~11 minutos** (calienta, referencia ejes, nivela; en el trabajo 44, de las
   18:56 a las 19:07:52) con `print_stats.state` todavía en `standby` aunque `idle_timeout` ya marca `Printing`.
   PrintWatch abre el trabajo solo cuando Klipper pasa a `printing`, así que esa fase no queda dentro del trabajo (sí
   en la bitácora, con origen `external`).

## Tiempo, filamento y duración

10. **Tiempo restante.** Se suponía que bastaban el avance del archivo o el ritmo de capas; medido contra el final real:

    | trabajo | avance del archivo | ritmo de capas | laminador (total del nombre − `print_duration`) |
    |---|---|---|---|
    | 43 (6 h) | 22,7 min de error medio | 53,5 min | **1,0 min** |
    | 44 (3,6 min) | 264,6 s | 80,4 s | **13,5 s** |

    El del laminador fue el único utilizable en ambos y es el que usa la web (el de avance solo si el archivo no trae
    estimación, marcado «poco precisa»). El de capas falla en el trabajo 43 porque una capa (z ≈ 93 mm) tardó 24 min a
    25 mm/s; el de avance, porque el archivo ya marca 7 % al empezar (el G-code inicial es parte del archivo).
    Límites del del laminador: en el trabajo 44 la impresión duró **162,0 s** de reloj de la impresora contra 148 s
    del nombre (**+9,4 %**; en el trabajo 43, +0,3 %), así que marca 0 en los últimos 14 s; y como `print_duration`
    arranca en 0 durante el calentamiento, al principio promete 148 s cuando faltan 214 s de reloj. Con dos
    impresiones el resultado se limita a eso. *Detalle:* `RESULTADOS.md` §1b, `analisis_trabajo_43.md`,
    `PROGRESO_FINAL.md`.
11. **Filamento.** Se sospechó que el cálculo por densidad sobrestimaba; la comparación era mala (el avance del archivo no
    es lineal respecto del filamento). Con el final: trabajo 43, **68.220 mm → 208,4 g** contra **201,83 g** del
    laminador (**+3,1 %**); trabajo 44, 94,1 mm → 0,287 g contra 0,28 g (**+2,5 %**). Se mantiene el cálculo por
    densidad (PETG, 1,27 g/cm³, 1,75 mm).
12. **La duración que mostraba la web era la que PrintWatch siguió el trabajo, no la real.** Trabajo 43: «2 h 45 min»
    contra **6 h 01 min** de la impresión (PrintWatch se unió al 45 %, en la capa 275). Se guarda y muestra ahora el reloj
    de la impresora (`print_duration`) con una nota de cuánto lo siguió PrintWatch; los trabajos viejos, sin ese dato,
    muestran solo la duración seguida. En el reporte PDF, el aviso «se unió ya al X %» se decide por la capa de la
    primera muestra (el trabajo 44 lo disparaba por error: el avance ya era 7 % en la capa 0).

## Volumen de datos y carga

13. **Telemetría:** una muestra por segundo; el trabajo 44 dio 206 muestras en 214 s, sin huecos de más de 3 s (el 43:
    9.434, con dos huecos de más de 5 s por los reinicios de Docker). Cada muestra pesa **~0,7 KB** de fila
    (685 B en el trabajo 44, 846 B en el 43 antes de quitar claves constantes de los sensores): ~4,7 a 5,8 MB por 2 h de
    impresión. La base entera (178 capturas, 2 trabajos de telemetría) pesa 18 MB.
14. **WebSocket de Moonraker:** un mensaje de estado cada 0,25 s en ambos estados; imprimiendo, **4,2 KB/s** (45 objetos,
    ~30 MB por 2 h; Moonraker ~11 % de CPU); quieta, 2,4 KB/s con 116 objetos. 54 campos solo se mueven imprimiendo.
15. **Fotos:** 1280×720, **~150 KB** cada una (4,8 MB por las 32 capas del trabajo 44; ~73 MB para 486 capas). Un cuadro
    negro pesa 15 KB.
16. **Carga de PrintWatch durante una impresión:** backend 0,2 a 1,8 % de CPU y ~100 a 115 MiB; worker de inferencia 0 % entre
    capas y pico de ~33 % (un hilo) en cada inferencia.
17. **Latencias por capa** (trabajo 44, 32 capas): de detectar el cambio de capa a la foto, 0,29 a 1,77 s (media 0,52 s);
    de la foto al resultado del modelo, 0,49 a 2,40 s (media 0,87 s); **de punta a punta, p90 2,5 s y máximo 3,2 s**. La
    detección no guarda el tiempo de inferencia del modelo, así que la latencia pura del ONNX no está medida.

## Atribución de origen y pausa

18. **Origen de los eventos** (trabajo 44): `M104 S250`, `M140 S0`, `START_PRINT EXTRUDER_TEMP=250 BED_TEMP=80` y
    `END_PRINT` quedaron como **`gcode_file`**, con la línea del archivo, su posición y la macro (`via_macro`). El paso
    `standby → printing` quedó como `external` (PrintWatch no distingue la pantalla de Fluidd), el fin como `printer`, y
    los cambios de temperatura de la preparación previa, sin archivo en curso, como `external`. Cadena de hashes
    íntegra (75 eventos al cerrar el trabajo 44). **Sin comprobar:** la atribución de los cambios de factor de
    velocidad desde la pantalla y desde Fluidd (la impresión terminó antes de poder probarlos).
19. **Pausa automática:** pausa tras 3 capas seguidas de *spaghetti* y 15 s de gracia, y al vencer PrintWatch envía el
    `pause`. No había forma de dejarla solo en aviso: se añadió `AUTO_PAUSE_MODE` (`on`, `warn`, `off`). En el trabajo 44,
    en modo `warn`, hubo **0 eventos «habría pausado»** (0 capas con defecto); la ruta solo se probó con la simulada.
    **No se probaron la pausa ni la reanudación** con la impresora real (Etapa C, sin autorización).
20. **Incidente de reanudación del 25-09:** no queda rastro en la impresora (144 MB de logs sin el archivo, sin
    `Move out of range`, y ninguno cruzable con esa fecha porque el reloj vuelve a 2020). Se sabe: el destino pedido,
    X = 292,424 mm, estaba **7,4 mm fuera** del límite (`position_max` 285); Y = 249,61 y Z = 28,401 estaban dentro;
    fue una reanudación del mismo trabajo (`print_duration` continuado, estado `error`); la pausa subió la Z a ~50 mm
    (macro `PAUSE_EXTERNAL`). El destino no coincide con ninguna posición fija de la configuración; la sospecha más
    razonable, **no demostrada**, es la secuencia de reanudación de Creality (comandos internos `BOX_*`, `RESUME_FLUSH`).
    Se añadió una guarda: una sola orden de reanudar a la vez, 20 s de enfriamiento y solo si la impresora dice `paused`.

## La cámara y la web

21. **La cámara de las pruebas no era la C922.** Era una «USB Camera» genérica (VID 5258, PID 4A55). Windows ya
    no tenía conectada la C922 (su última llegada a ese equipo fue el 22-09). La focal estimada de la calibración salió de **~1.490 y ~1.499 px** (dos
    calibraciones, con la cama en otra posición) contra ~907 px de una C922 a 1280×720: un campo de visión de ~52° y no
    de 78°. Con 907 px fijos las cuatro marcas no cuadran (error de hasta 63 mm sobre la cama), así que la focal no se
    fija: es la de esa cámara. Con la C922 se recalibra. La calibración ahora permite fijar la focal conocida y muestra
    el error de cada marca; una focal distinta de la de la C922 es solo una nota, no un aviso.
22. **El video salió negro** cuando se desconectó y se cambió la cámara: `capture` abría la cámara por índice (`0`) y el
    cuadro negro es «reciente», así que la web lo mostraba como video vivo. Ahora `capture` trata un cuadro todo negro
    como «sin señal» y no lo publica, y la cámara puede elegirse por nombre (`name:C922`). *Sin probar con hardware*
    (el equipo de casa no tiene cámara conectada).
23. **Con la cámara en esa posición el modelo no puede ver la pieza:** está baja y de frente, se ve la máquina y el
    cabezal, no la superficie de la cama. Por eso «0 defectos» en el trabajo 44 no dice nada de la pieza, y el mapa de
    la cama contra un defecto real **no se pudo comprobar**. Sí coincide la pieza con la ruta del cabezal: el cubo en
    (130, 130) mm con polígono de 126,8 a 133,2 mm, y el cabezal se movió entre X e Y de 127 a 133 mm.
24. **El modelo nunca se ha evaluado con imágenes reales de la cámara final.** Sus métricas salen de fotos de Roboflow
    Universe (FP32: precisión 0,997 y recall 0,921 a nivel imagen; 9.457.164 parámetros, ~21,3 GFLOPs). Faltan
    `args.yaml`, `results.csv`, `best.pt` y el dataset.
25. **Cosas de la web que solo aparecieron con datos reales:** la página en vivo se ensanchaba en el celular; el
    stream mostraba un cuadro de hace horas como si fuera vivo; la tarjeta del último trabajo decía «Capa 0 / 486»
    (usaba la capa en vivo de la impresora quieta) y la duración seguida en vez de la real; el login fallaba porque
    el `.env` de la web apuntaba a una IP vieja del equipo; la miniatura de video del Panel mantenía una conexión
    abierta por tarjeta (~1 MB/s) y un navegador solo admite ~6 conexiones por servidor, que se agotan con 6 pestañas
    con video: ahora la miniatura pide una foto cada 2 s y el video en vivo se cierra con la pestaña oculta. La
    miniatura negra concreta que vio Samuel **no se pudo reproducir** (se pintaba bien en la demostración); lo
    medido es lo anterior.
26. **Docker en WSL2** se reinicia solo si no hay una sesión `wsl -- sleep infinity` abierta (con la impresión en
    curso, el backend se reinició 3 veces en 2 minutos sin perder el trabajo).

## Pruebas

27. Backend: de 143 pruebas al empezar el laboratorio a **156**; `capture`: **14** (nuevas); web: **12** (nuevas, con
    `vitest`); la web compila sin errores.

## Sin hacer (necesita la impresora o la cámara)

28. Calibrar con la C922; los dos cambios de factor de velocidad (pantalla y Fluidd); una impresión más larga con la
    pieza visible; la Etapa C (pausa y reanudación, con autorización); la impresora .21; los datos del entrenamiento del
    modelo; los precios y potencias reales.
