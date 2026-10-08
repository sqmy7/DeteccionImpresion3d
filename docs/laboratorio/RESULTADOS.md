# Resultados del laboratorio: Creality Hi real imprimiendo (2026-10-08)

Sesión en la red SalaSteam_UIS, con la Creality Hi-3422 (192.168.10.22) imprimiendo el trabajo 43
(`CAJA LISTA CARA ADALOVE LISTA PARA IMPRIMIR (1).stl_PETG_6h0m27s.gcode`, 486 capas, PETG, boquilla a
250 °C y cama a 80 °C). **Todo lo que se hizo con la impresora fue de solo lectura** (GET a Moonraker y
suscripciones por WebSocket); no se envió G-code ni ninguna orden, y la impresión no se interrumpió. El
detalle por paso está en `docs/PROGRESO_TELEMETRIA.md`; los volcados, en `docs/laboratorio/descubrimiento/`
(los logs y muestras grandes no se versionan).

Estado: **la impresión terminó** (trabajo 43, `completed`, 16:58:42 hora de Colombia, capa 486). El análisis
del cierre está en la sección 1b y en `docs/laboratorio/analisis_trabajo_43.md`. Lo que depende de la
impresora quieta (calibrar la cámara, arrancar `capture`, desplegar el backend) sigue pendiente de ti.

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

## 1b. Cierre del trabajo 43 (análisis con la base de PrintWatch, solo SELECT)

- **Cierre correcto:** `completed`, fin 16:58:42, 9.434 muestras (2 h 45 min con telemetría), 210 capas (275 a 486:
  PrintWatch se unió con la impresión al 45 %), cadena de eventos íntegra (6 eventos; el último hash está en
  `analisis_trabajo_43.md`). Dos huecos de más de 5 s en las muestras (el mayor, 33 s: los reinicios de Docker).
  Cero alertas, cero eventos de intervención, cero detecciones (`capture` apagado).
- **Duración:** el trabajo completo duró ~21.690 s (11.811 s al engancharnos más 9.879 s observados) contra los
  21.627 s del nombre del archivo: **+63 s (+0,3 %)**.
- **Filamento:** 68.220 mm → 208,4 g por densidad; laminador 201,83 g (+3,1 %). Costo con precios de ejemplo
  ($ 80.000/kg, $ 900/kWh): ~17.000 COP, de los cuales ~360 son energía. La energía solo cubre el tramo con
  telemetría (0,40 kWh: boquilla 55 Wh, cama 345 Wh), con potencias supuestas de 50 W y 300 W.
- **Tiempo restante reconstruido** (minutos; minuto 0 = primera muestra, a 2 h 45 min del final):

| minuto | capa | progreso | real | avance | capas | laminador |
|---|---|---|---|---|---|---|
| 0 | 274 | 0,45 | 165 | - | - | 164 |
| 30 | 346 | 0,53 | 135 | 163 | 58 | 134 |
| 60 | 409 | 0,65 | 105 | 101 | 34 | 104 |
| 80 | 453 | 0,75 | 85 | 68 | 15 | 84 |
| 100 | 466 | 0,76 | 65 | 77 | 10 | 64 |
| 120 | 476 | 0,77 | 45 | 84 | 6 | 44 |
| 150 | 481 | 0,86 | 15 | 50 | 4 | 14 |

| método | error absoluto medio | error con signo (+ = demasiado) |
|---|---|---|
| avance del archivo | 22,7 min (74 %) | +17,4 min |
| ritmo de capas | 53,5 min (73 %) | -53,5 min |
| laminador (nombre del archivo − `print_duration`) | **1,0 min (5 %)** | -1,0 min |

  Con una sola impresión de una sola pieza, la conclusión se limita a eso: el estimador del laminador
  fue el único utilizable. El de capas falla justamente porque el final de esta pieza es lento.
- **Reporte PDF** del trabajo (`reporte_trabajo_43.pdf`): se generó con los datos reales y se corrigió lo que
  se veía mal (eje degenerado de la gráfica de porcentajes, estimación derivada del nombre para trabajos
  guardados antes, aviso de que PrintWatch se unió al 45 %, tiempo real de Klipper cuando existe). El tiempo
  del laminador y el real concuerdan al 0,3 %.

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
7. **El filamento por densidad resultó bien, y mi sospecha anterior estaba equivocada.** A mitad de la impresión
   comparé el filamento acumulado con la fracción de los 201,83 g proporcional al avance del archivo y parecía
   sobrestimar ~35 %; el avance del archivo no es lineal respecto del filamento, así que esa comparación no valía.
   Con el final: 68.220 mm de `print_stats.filament_used` dan **208,4 g** por densidad (PETG 1,27 g/cm³, 1,75 mm)
   contra **201,83 g** del laminador: **+3,1 %** (compatible con la purga y la densidad nominal). Se mantiene el
   método por densidad.

8. **El tiempo restante de la web era erróneo** en trabajos tomados a mitad de impresión y ningún estimador
   por ritmo sirve. Medido contra el final real (tabla en 1b): el del laminador (tiempo total del nombre del
   archivo menos `print_duration`) tiene **1,0 min** de error medio (5 %); el avance del archivo, 22,7 min
   (74 %); el ritmo de capas, 53,5 min. Una capa (z ≈ 93 mm) tardó 24 min a 25 mm/s y las siguientes ~3 min:
   el tramo final de esa pieza es mucho más lento que el resto. La web usa ahora el del laminador, y el de
   avance (marcado "poco precisa") solo si el archivo no trae estimación.

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
3. Decidido el cálculo de gramos: se mantiene la densidad (ver 2.7). Falta solo revisar el PDF con los precios
   reales.

4. ~~Elegir el cálculo del tiempo restante~~: hecho (laminador; ver 1b y 2.8).

5. **Precios reales** (filamento y kWh) en "Precios y potencias".
6. Opcional: probar, ya sin imprimir, el stream de la cámara si aparece alguna URL publicada.
