# Resultados del laboratorio: Creality Hi real imprimiendo (2026-10-08)

Sesión en la red SalaSteam_UIS, con la Creality Hi-3422 (192.168.10.22) imprimiendo el trabajo 43
(`CAJA LISTA CARA ADALOVE LISTA PARA IMPRIMIR (1).stl_PETG_6h0m27s.gcode`, 486 capas, PETG, boquilla a
250 °C y cama a 80 °C). **Todo lo que se hizo con la impresora fue de solo lectura** (GET a Moonraker y
suscripciones por WebSocket); no se envió G-code ni ninguna orden, y la impresión no se interrumpió. El
detalle por paso está en `docs/PROGRESO_TELEMETRIA.md`; los volcados, en `docs/laboratorio/descubrimiento/`
(los logs y muestras grandes no se versionan).

Estado: **la impresión seguía en curso al escribir esto** (capa ~337 de 486). Lo que depende de que la
impresora esté quieta (Paso 4) y el cierre de las comparaciones con el final real quedan al final, como
pendiente.

## 1. Qué se comprobó de verdad

| Tema | Resultado | Cómo se sabe |
|---|---|---|
| PrintWatch sigue una impresión real | **Sí**: trabajo 43, muestras cada segundo (1.416 en 23 min), posición, temperaturas, factores, sensores | consultas a la base y a la API |
| Listener tras reinicios | **Sí**: tras 3 reinicios del backend en 2 min retomó el trabajo abierto sin duplicarlo | log del backend |
| Bitácora con la impresión estable | **Sí**: ningún evento falso en 25 min (solo las 3 conexiones); cadena de hashes íntegra | `/events/verify` |
| `motion_report` (posición real) | **Sí**, a ~4 Hz | medición del WebSocket |
| `toolhead.position` como alternativa | **No sirve**: va ~100 mm por delante (mediana; p90 162 mm) | comparación en 1.189 pares |
| Corrección del reloj de la impresora | Necesaria: el reloj marca 2020-01-01 desde cada arranque (-213.636.671 s) | encabezado `Date` y `gcode_store` |
| Sensores de filamento | **Sí, cinco** (cabezal, uno más y tres de la caja CFS) | objetos `filament_switch_sensor *` |
| Costo de la medición del WebSocket | 4,2 KB/s con 45 objetos (1.491 mensajes en 300 s); Moonraker ~11 % de CPU | `ws_medicion_printing.json`, `proc_stats` |
| Carga de PrintWatch | Backend 0,35 % de CPU y 115 MiB; base de datos de 10 MB | `docker stats` |
| Peso de la telemetría | **1.036 bytes por muestra** (714 son el campo de sensores extra): ~7,5 MB por cada 2 h de impresión | `pg_total_relation_size` |
| Web con datos reales (escritorio y celular) | Funciona; ver las correcciones de la sección 2 | capturas y `overflow.py` |
| Reporte, costo, mapa y salud | Responden con datos reales (reporte y salud sin probar a fondo: no hay trabajos terminados con telemetría) | API |

## 2. Qué resultó distinto de lo supuesto

Cada una de estas suposiciones de las Fases 0 a 5 estaba mal o incompleta; ya están corregidas en el
código (el backend desplegado se reconstruye cuando termine la impresión).

1. **La cama no mide lo que dicen los ejes.** Klipper reporta recorrido de 285 × 273 mm (incluye el
   cortador de filamento, en X = 279,6). La cama es de 260 × 260 (malla de 10 a 250). Se usaba el
   recorrido, lo que habría torcido la calibración, el mapa y el reporte.
2. **Los sensores de filamento 3 a 5 siempre dicen "sin filamento"** (ranuras de la caja CFS, que no está
   conectada). Con la lógica anterior, todo `under_extrusion` habría ganado +0,6 de puntaje combinado.
   Ahora solo cuenta un sensor que haya visto filamento durante ese trabajo.
3. **No existe el objeto `fan`.** El ventilador de capa es `output_pin fan0`; `fan_speed` quedó vacío
   en todas las muestras. Ahora se lee de ahí.
4. **Los metadatos del laminador no son los esperados.** No hay `estimated_time`, `filament_total` ni
   `filament_weight_total`; hay `filament_used_g` (lista de cadenas) y `layer_count`. El tiempo estimado
   solo está en el **nombre del archivo** (`..._PETG_6h0m27s.gcode`): se toma de ahí, marcado como tal.
5. **Moonraker no publica cámaras** (`/server/webcams/list` vacío): no hay una cámara interna que se
   pueda leer por esa vía. No se probó ninguna URL adivinada.
6. **Las potencias de los calentadores no están en la configuración.** Solo hay PID y `max_temp`; los
   supuestos de 50 W (boquilla) y 300 W (cama) **siguen sin verificarse** y no se cambiaron.
7. **El cálculo de filamento por densidad parece sobrestimar** (~134 g contra ~99 g proporcionales al
   avance, con el laminador diciendo 201,83 g para el archivo completo): `print_stats.filament_used`
   cuenta también las retracciones. Hay que comprobarlo con el final de la impresión (ver pendientes).
8. **El tiempo restante de la web era erróneo** en trabajos tomados a mitad de impresión (decía ~16 min
   cuando faltaban más de una hora). Se corrigió el cálculo, pero el avance del archivo (`progress`)
   tampoco es lineal en el tiempo en esta impresión: la web dice ~2 h 47 min, el ritmo de capas sugiere
   ~70 min y el laminador ~2 h 40 min. Se evalúa contra el final real.
9. **El stream de video mostraba, sin avisar, un cuadro de hace horas** (el que quedó en Redis de una
   sesión de pruebas). Ahora dice "sin señal" si el cuadro tiene más de 15 s.
10. **La página en vivo se ensanchaba en el celular** (una columna sin `min-w-0` crecía por los chips de
    sensores). Corregido y comprobado con el medidor de desborde.
11. **Docker en WSL2 se reinició solo** por no haber una sesión `wsl -- sleep infinity` abierta (es una
    precondición documentada). Con la impresión en curso, el backend se reinició 3 veces en 2 minutos
    sin perder el trabajo. Se abrió esa sesión y no volvió a pasar.
12. **Peso de la telemetría:** ~1 KB por muestra, no 379 bytes como en la simulada, por las claves
    constantes `enabled` de los 5 sensores; se quitaron (y los `output_pin` que no son ventiladores).

## 3. Qué sigue sin comprobarse

- **Atribución de origen con datos reales** (`console`, `external`, `gcode_file`): la impresión ya estaba
  en marcha, así que no se vio la secuencia de inicio, y no se provocó nada (exigiría mandar órdenes).
  El índice del archivo sí funcionó (10 MB, 1.519 comandos relevantes en ~10 s).
- **Fotos, detecciones, pausa automática y mapa de defectos reales**: `capture` está apagado (a propósito:
  arrancarlo durante esta impresión reactivaría la pausa automática).
- **Calibración de la C922**, reporte PDF de un trabajo real, precios y costo reales.
- **Salud**: hacen falta al menos 6 trabajos terminados con telemetría.
- **Potencias reales de los calentadores y cámara interna** (ver 2.5 y 2.6).
- **Si la Hi publica `estimated_time`** en algún otro lugar: no aparece en ningún objeto ni en los
  metadatos de los cuatro archivos revisados.

## 4. Incidente de reanudación del 25-09-2026

**Lo que se puede afirmar (certeza alta):**
- **No queda rastro en la impresora.** Ninguno de los 144 MB de logs (`klippy.log` actual y 5 rotaciones de
  mayo, `moonraker.log` y 2 de mayo) menciona el archivo `BOX FINAL...`, ni `Move out of range`, ni una
  pausa en la posición esperada (~5,1 MB del archivo de 5.157.891 bytes). `gcode_store` solo guarda desde el
  último arranque. Esta parte de la evidencia se perdió; no se puede reconstruir con hora exacta.
- **El destino del movimiento estaba fuera de rango**: X = 292,424 contra `stepper_x.position_max = 285`
  (7,4 mm de más). Y = 249,61 y Z = 28,401 sí estaban dentro de los límites.
- **Fue una reanudación del mismo trabajo, no un inicio nuevo**: el historial de Moonraker tiene una sola
  entrada para ese archivo, con `print_duration` continuado (7.448 s → 7.456 s) y estado `error`.
- **La pausa subió la Z a ~50 mm**, coherente con la macro `PAUSE_EXTERNAL` (si Z < 48, sube hasta 50) y con
  el `z_pos = 49,929` registrado.

**Lo que se puede afirmar con certeza media:**
- **El destino no es ninguna posición fija de la configuración**: extrusión (X −18,5, Y 130), corte (X 279,6,
  Y 130), pre-corte (X 240, Y 130), estacionamiento de pausa (X 275, Y 136,5), fin de impresión (X 0, Y 260),
  cancelación (X 10, Y 260) y el final del propio archivo (X 0, Y 180). Debió de ser un movimiento
  **calculado o relativo**.
- **El final del archivo no lo causa** (`M106 S0`, `G1 X0 Y180`, `END_PRINT`: todo dentro de los límites; el
  analizador no encontró ningún movimiento fuera de rango en los cuatro archivos).
- **La secuencia de reanudación de Creality usa comandos internos** (`BOX_GO_TO_EXTRUDE_POS`,
  `RESUME_FLUSH`, `BOX_NOZZLE_CLEAN`, `BOX_TIGHTEN_UP_ENABLE`) cuyo código no es legible por Moonraker. Es
  la sospecha más razonable, pero **no está demostrada**.

**Lo que no se puede saber con lo que hay:** quién mandó la orden (PrintWatch, consola o pantalla), si llegó
dos veces, y qué hizo Klipper con los ejes en esos segundos. La tabla `printer_events` y el registro de
comandos de PrintWatch empezaron en octubre, y el contenedor del backend de entonces ya no existe.
No se hizo ninguna prueba de pausa ni de reanudación para comprobarlo, y no se debe hacer sin tu orden.

**Recomendación para PrintWatch:** mantener que nunca reanuda por su cuenta (ya es así). Con esta
secuencia de reanudación de Creality, una reanudación remota merece tratarse como riesgosa, y la bitácora
ya registra cada orden enviada y cada cambio de estado, de modo que el próximo incidente sí quedará con hora
exacta.

## 5. Pendientes (cuando termine la impresión; esperan tu aviso)

1. **Desplegar el backend** con las correcciones (reconstruir el contenedor): no se hizo para no
   reiniciarlo durante la impresión.
2. **Reiniciar `capture`** (para que guarde la hora de cada cuadro) y **calibrar la C922** desde la web,
   con la impresora quieta.
3. **Reporte PDF** del trabajo 43 terminado; comprobar el tiempo del nombre del archivo contra el real y
   **filamento usado contra los 201,83 g del laminador** para decidir cómo calcular los gramos.
4. **Elegir el cálculo del tiempo restante** comparando las tres estimaciones con el final real.
5. **Precios reales** (filamento y kWh) en "Precios y potencias".
6. Opcional: probar, ya sin imprimir, el stream de la cámara si aparece alguna URL publicada.
