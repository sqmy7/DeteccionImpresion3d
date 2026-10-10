-- DESHACER la propuesta de roi_camara_36_aplicar.sql: la cámara 36 vuelve a analizarse con el fotograma completo (roi vacío, como estaba el 2026-10-09).
-- Cómo ejecutarlo (PowerShell, desde la raíz del repo):
--   Get-Content docs\laboratorio\etapa_c2\roi_camara_36_deshacer.sql | wsl docker exec -i infra-postgres-1 sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -f -'
-- Las detecciones ya guardadas conservan la región con la que se hicieron (raw_output.frame.roi), así que no hay nada más que revertir.

update cameras set roi = null where id = 36;

select id, name, roi from cameras where id = 36;   -- debe salir vacío
