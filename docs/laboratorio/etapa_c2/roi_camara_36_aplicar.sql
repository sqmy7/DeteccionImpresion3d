-- PROPUESTA, NO EJECUTADA: región de interés de la cámara 36 (recorta el fotograma a la cama antes de la inferencia).
-- Valores en píxeles del fotograma completo de 1280x720: x, y = esquina superior izquierda; w, h = ancho y alto.
-- Solo se aplica si ahora no hay ninguna región (roi vacío), para no pisar un valor que alguien haya puesto.
-- Cómo ejecutarlo (PowerShell, desde la raíz del repo):
--   Get-Content docs\laboratorio\etapa_c2\roi_camara_36_aplicar.sql | wsl docker exec -i infra-postgres-1 sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -f -'
-- Se deshace con roi_camara_36_deshacer.sql. Surte efecto en la siguiente capa que se analice (el worker lee la región en cada mensaje): no hace falta reiniciar nada.

select id, name, roi from cameras where id = 36;   -- antes: roi debe salir vacío

update cameras
set roi = '{"x": 100, "y": 300, "w": 1180, "h": 420}'::jsonb
where id = 36 and roi is null;

select id, name, roi from cameras where id = 36;   -- después: la región nueva
