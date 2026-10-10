-- C2, solo lectura. Sustituir __JOB__ por el id del trabajo (por ejemplo: sed "s/__JOB__/47/g" c2_capturas.sql > /tmp/c.sql) y ejecutar con psql.
\echo === 1. Capturas por capa (hora local), con el hueco respecto a la captura anterior
with caps as (
  select l.layer_number, l.detected_at, lc.captured_at, d.max_confidence, d.has_defect,
         lag(lc.captured_at) over (order by l.layer_number) as anterior
  from layers l
  left join layer_captures lc on lc.layer_id = l.id
  left join detections d on d.capture_id = lc.id
  where l.job_id = __JOB__)
select layer_number as capa,
       to_char(detected_at at time zone 'America/Bogota','HH24:MI:SS') as capa_detectada,
       to_char(captured_at at time zone 'America/Bogota','HH24:MI:SS') as captura,
       round(extract(epoch from (captured_at - detected_at))::numeric, 1) as retraso_s,
       round(extract(epoch from (captured_at - anterior))::numeric, 1) as desde_la_anterior_s,
       max_confidence as confianza, has_defect as defecto
from caps order by layer_number;
\echo === 2. Capas sin captura
select count(*) as capas_totales, count(*) filter (where lc.id is null) as capas_sin_captura
from layers l left join layer_captures lc on lc.layer_id = l.id where l.job_id = __JOB__;
\echo === 3. Pausas y reanudaciones del trabajo (bitacora)
select to_char(ts at time zone 'America/Bogota','HH24:MI:SS.MS') as hora, value_before as antes, value_after as despues, origin
from printer_events where print_job_id = __JOB__ and event_type = 'state_changed' and (value_after in ('"paused"') or value_before = '"paused"') order by ts;
\echo === 4. Capturas hechas durante cada pausa (entre paused y la reanudacion) y primera captura tras reanudar
with ev as (
  select ts, value_after, lead(ts) over (order by ts) as siguiente, lead(value_after) over (order by ts) as siguiente_estado
  from printer_events where print_job_id = __JOB__ and event_type = 'state_changed'),
pausas as (select ts as inicio, siguiente as fin from ev where value_after = '"paused"' and siguiente_estado = '"printing"')
select to_char(p.inicio at time zone 'America/Bogota','HH24:MI:SS') as pausa_desde,
       to_char(p.fin at time zone 'America/Bogota','HH24:MI:SS') as reanudada,
       (select count(*) from layer_captures lc join layers l on l.id = lc.layer_id where l.job_id = __JOB__ and lc.captured_at >= p.inicio and lc.captured_at < p.fin) as capturas_en_la_pausa,
       (select to_char(min(lc.captured_at) at time zone 'America/Bogota','HH24:MI:SS') from layer_captures lc join layers l on l.id = lc.layer_id where l.job_id = __JOB__ and lc.captured_at >= p.fin) as primera_captura_tras_reanudar,
       (select round(extract(epoch from (min(lc.captured_at) - p.fin))::numeric, 1) from layer_captures lc join layers l on l.id = lc.layer_id where l.job_id = __JOB__ and lc.captured_at >= p.fin) as segundos_hasta_ella,
       (select min(l.layer_number) from layer_captures lc join layers l on l.id = lc.layer_id where l.job_id = __JOB__ and lc.captured_at >= p.fin) as su_capa
from pausas p order by p.inicio;
