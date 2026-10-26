# PrintWatch — contexto del proyecto (memoria)

Corte: 2026-10-09. Autor: Samuel (UIS, Ing. en Inteligencia Artificial, Barrancabermeja). Compañero: Adrian Stiven Meneses Ávila. Docente: Jheyston Serrano.

## Reglas fijas
- Samuel implementa con Claude Code en VS Code (repo local `C:\Users\SAMUEL\Documents\DeteccionImpresion3d`, GitHub `sqmy7/DeteccionImpresion3d`). Quiere prompts listos para pegar; habla informal; paso a paso cuando lo pide.
- **Meta final:** la web detecta un fallo inminente, interviene con éxito y muestra el reporte y todos los parámetros necesarios de la impresora.
- El informe de laboratorio (LaTeX) **nunca menciona a Claude**. Commits **sin** Co-Authored-By.
- Autorizaciones explícitas antes de pruebas físicas: "autorizo la C" (pausa inducida), "autorizo cancelar" (cancelación real), "autorizo la limpieza" (Etapas D–F). No actuar sobre la impresora sin ellas.
- Mantener `AUTO_PAUSE_MODE=warn` hasta validar con spaghetti real.
- No implementar el mosaico (tiling) hasta ver resultados de la Parte A/B y el OK de Samuel.
- Nota: el checkout de la nube solo tiene el commit inicial; el repo local real tenía `main` en fe8a90a, 77 commits sin push, ramas `incidente-web` y `lab-ausente`.

## Sistema
- Impresora Creality Hi 3D (Klipper/Moonraker) en 192.168.10.22:7125 (la .21 nunca respondió). Reloj mal (2020); 8–11 min de preparación en `standby`; 5 sensores de filamento; cama 260×260, X −19..285, Y −7..273; posición real = `motion_report.live_position`.
- Backend FastAPI + PostgreSQL + Redis (Docker/WSL2); `capture` nativo en Windows, se arranca a mano (no lo hace start.ps1; una consola de Administrador no abre la cámara); worker ONNX; web React en :5173 (`frontend/.env` VITE_API_BASE_URL=http://localhost:8000).
- Modelo YOLO11s propio, 6 clases, `yolo11s-trained-v1-fp32`; umbral 0.25; test 841 imágenes: precisión 0.997, recall 0.921 (imagen). Entrada 640×640 por estiramiento; NMS agnóstico IoU 0.45. `under_extrusion` recall 0.685. Nunca evaluado con spaghetti real en nuestra cámara.
- Cámara genérica "USB Camera" provisional (focal ~1490–1499 px); C922 definitiva (BD fila 36, source_uri 0). `cameras.roi` vacío.
- Incidentes: tabla `incidents`; `INCIDENT_CLASSES=spaghetti,layer_shift`; `INCIDENT_MIN_CONFIDENCE=0.50`; racha = 3 capas seguidas; gracia 15 s; confirmación de pausa hasta 20 s; cancelar exige escribir "CANCELAR"; bitácora con cadena de hashes.
- Acciones: pausar/reanudar/cancelar devuelven 202 tras `ACCEPT_WAIT_SECONDS=3.0`; 409 contra segundo reanudar/cancelar en curso (tope 90 s); JWT 60 min con `POST /auth/refresh`, tope 24 h; orden registrada antes de enviarse (atribuida a `printwatch`, ventana 120 s); `pause_safely` lee estado primero.
- Red: cable (192.168.10.105) para la impresora, Wi-Fi para internet, métrica cable 100; VPN apagada. La suspensión del PC hizo perder una pieza: evitarla.

## Hallazgos clave
- Etapa A: latencia punta a punta p90 2.5 s, máx 3.2 s. Etapa C real (trabajo 47): clic→paused ~1 s, clic→printing ~65 s, 86/86 capturas, cadena íntegra. Sin probar: segundo clic (409) en real.
- Trabajo 47: 21 detecciones, **todas falsas** (pieza blanca sobre el escritorio); con `on` habría pausado una pieza sana. Subir umbral no sirve. ROI propuesto: no aplicar (deformación 2.81×).
- Enredo pequeño (48×43 px) no se detecta en imagen completa; recortes de 400–800 px sí (0.50–0.74). Enredo grande detectado 0.319 (margen 0.069). Plan: dos recortes solapados ~800×450 por capa.
- Incidente 25-sep (trabajo 35): `Move out of range: 292.424 …` al reanudar; causa sin determinar, hipótesis "iniciar vs reanudar" no respaldada.

## Pendientes (orden)
1. Experimento de mosaico (Parte A offline, Parte B foto limpia) y decidir.
2. Aviso web "captura detenida" + script de arranque de `capture`.
3. Conectar y recalibrar C922.
4. Prueba controlada de spaghetti real; pausa inducida; cancelación real; segundo clic 409.
5. Decidir modo final; Etapas D–F.
6. Actualizar el Docs del profesor (27cd9187-f432-40ca-8172-0c94414bcee6, desactualizado: 2026-10-05).
- Estudio guiado pendiente: Idea 5, tamaño de salida de convolución ⌊(n+2p−k)/s⌋+1 (7×7,k3,p0,s2→3×3; 80×80,k3,p1,s2→40×40).

## Entregables
- `informe_printwatch.tex` (LaTeX, actualizado 2026-10-09), sin mención a Claude. Portada: Samuel Esteban Rodríguez Marín 2254274; Adrian aún con "CÓDIGO" pendiente.
