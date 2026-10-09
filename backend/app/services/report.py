"""PDF report of one print job, generated on request with the data as it is at that moment:
summary (real vs slicer-estimated time and filament, the cost estimate), temperature and speed
charts with the defects and interventions marked, the defect map of the bed, every defect with its
combined score, the job's event log and the last hash of the printer's event chain, so the log can
be checked later against the printed copy.

Drawn with fpdf2's vector primitives (no image libraries). The text uses the PDF core fonts, so it
is kept to Latin-1, which covers Spanish."""

import math
from datetime import datetime, timedelta, timezone

from fpdf import FPDF
from fpdf.enums import TextEmphasis, XPos, YPos
from fpdf.fonts import FontFace
from sqlalchemy import Float, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Alert, Detection, Layer, LayerCapture, Printer, PrintJob, TelemetrySample
from app.services import costs, defect_map, fusion, printer_events, telemetry, timeline

BOGOTA = timezone(timedelta(hours=-5))  # Colombia keeps UTC-5 all year
MAX_CHART_POINTS = 600
MAX_EVENT_ROWS = 150

CLASS_LABELS = {
    "spaghetti": "Spaghetti",
    "warping": "Warping",
    "stringing": "Stringing",
    "layer_shift": "Desplazamiento de capa",
    "under_extrusion": "Sub-extrusión",
    "blob_over_extrusion": "Exceso de material (informativa)",
}
CLASS_CODES = {"spaghetti": "SP", "warping": "WA", "stringing": "ST", "layer_shift": "LS", "under_extrusion": "UE",
               "blob_over_extrusion": "BL"}
# Okabe-Ito like the web, a shade darker where the web's color is too light for white paper.
CLASS_COLORS = {"spaghetti": (213, 94, 0), "warping": (230, 159, 0), "stringing": (190, 170, 0), "layer_shift": (204, 121, 167),
                "under_extrusion": (0, 114, 178), "blob_over_extrusion": (120, 130, 145)}
INFORMATIONAL = {"blob_over_extrusion"}

STATUS_LABELS = {"running": "En curso", "completed": "Completado", "failed": "Fallido", "cancelled": "Cancelado"}
ORIGIN_LABELS = {"printwatch": "PrintWatch", "console": "Consola", "gcode_file": "Archivo G-code", "printer": "Impresora",
                 "external": "Externo", "monitor": "Monitor"}
EVENT_LABELS = {
    "monitor_connected": "PrintWatch se conectó", "monitor_disconnected": "PrintWatch perdió la conexión",
    "state_changed": "Cambio de estado", "printwatch_command": "Orden de PrintWatch", "target_changed": "Temperatura objetivo",
    "speed_factor_changed": "Factor de velocidad", "flow_factor_changed": "Factor de flujo", "fan_changed": "Ventilador",
    "z_offset_changed": "Desfase de Z", "object_excluded": "Objeto excluido", "filament_sensor_changed": "Sensor de filamento",
    "klippy_state_changed": "Estado de Klipper", "klippy_disconnected": "Klipper desconectado", "klippy_shutdown": "Klipper apagado",
    "klippy_ready": "Klipper listo", "console_command": "Comando de consola", "gcode_error": "Error de G-code",
}
STATE_LABELS = {"standby": "En espera", "printing": "Imprimiendo", "paused": "Pausada", "complete": "Completada",
                "cancelled": "Cancelada", "error": "Error"}
INTERVENTION_TYPES = {"target_changed", "speed_factor_changed", "flow_factor_changed", "fan_changed", "z_offset_changed",
                      "object_excluded"}

INK, MUTED, FAINT, LINE, LIGHT = (33, 37, 41), (90, 98, 108), (140, 148, 158), (210, 214, 220), (243, 245, 247)
NOZZLE, BED, SPEED, FLOW, FAN = (213, 94, 0), (0, 114, 178), (0, 158, 115), (204, 121, 167), (140, 148, 158)
DEFECT_MARK, INTERVENTION_MARK, PAUSE_MARK = (230, 159, 0), (120, 130, 145), (213, 94, 0)

_REPLACEMENTS = {"→": "->", "←": "<-", "≥": ">=", "≤": "<=", "−": "-", "–": "-", "—": "-", "…": "...", "“": '"', "”": '"',
                 "‘": "'", "’": "'", "σ": "sigma", "√": "raiz de ", "∏": "producto de ", "•": "-", "≈": "~"}


def _t(text) -> str:
    """Text the core fonts can print (Latin-1)."""
    text = "" if text is None else str(text)
    for old, new in _REPLACEMENTS.items():
        text = text.replace(old, new)
    return text.encode("latin-1", "replace").decode("latin-1")


def _num(value: float | None, digits: int = 1) -> str:
    if value is None:
        return "-"
    text = f"{value:,.{digits}f}"
    return text.replace(",", "\x00").replace(".", ",").replace("\x00", ".")


def _grams(value: float | None) -> str:
    """Grams with one decimal, or two under 1 g (a short print weighs 0,28 g, not 0,3)."""
    if value is None:
        return "-"
    return _num(value, 2 if abs(value) < 1 else 1)


# The first sample of a job followed from the start is at layer 0 or 1; a job joined mid-print starts at the
# layer the printer was on.
_FIRST_LAYER_SLACK = 2
# With no layer in the first sample, only a share this large says the print was already well under way.
_LATE_PROGRESS = 0.15


def joined_late(first_layer: int | None, first_progress: float | None) -> bool:
    """Whether PrintWatch joined a print that was already under way, from the layer of its first sample.
    The file progress is no good for this: it starts above 0 (job 44 began at 7 % in layer 0, because the
    start G-code is part of the file and a 2,5 minute print is mostly that), so on a short file it called a
    job followed from the start a late one."""
    if first_layer is not None:
        return first_layer > _FIRST_LAYER_SLACK
    return first_progress is not None and first_progress > _LATE_PROGRESS


def _money(value: float | None, currency: str) -> str:
    if value is None:
        return "-"
    return f"{_num(value, 0 if abs(value) >= 100 else 2)} {currency}"


def _duration(seconds: float | None) -> str:
    if seconds is None:
        return "-"
    seconds = int(round(seconds))
    hours, rest = divmod(seconds, 3600)
    minutes, secs = divmod(rest, 60)
    if hours:
        return f"{hours} h {minutes:02d} min"
    if minutes:
        return f"{minutes} min {secs:02d} s"
    return f"{secs} s"


def _local(moment: datetime | None, seconds: bool = True) -> str:
    if moment is None:
        return "-"
    return moment.astimezone(BOGOTA).strftime("%d/%m/%Y %H:%M:%S" if seconds else "%d/%m/%Y %H:%M")


def _value(field: str | None, value) -> str:
    if value is None:
        return "-"
    if isinstance(value, bool):
        return "sí" if value else "no"
    if isinstance(value, (int, float)):
        if field and field.endswith(".target"):
            return f"{value:.0f} °C"
        if field in ("gcode_move.speed_factor", "gcode_move.extrude_factor") or (field or "").endswith(".speed"):
            return f"{round(value * 100)} %"
        if field == "gcode_move.homing_origin[2]":
            return f"{value:+.3f} mm"
        return str(value)
    if field == "print_stats.state":
        return STATE_LABELS.get(str(value), str(value))
    return str(value)


def _field_name(field: str | None) -> str:
    names = {"extruder.target": "Boquilla", "heater_bed.target": "Cama", "gcode_move.speed_factor": "Velocidad",
             "gcode_move.extrude_factor": "Flujo", "fan.speed": "Ventilador de capa", "gcode_move.homing_origin[2]": "Desfase de Z"}
    return names.get(field or "", field or "")


def describe_event(event) -> str:
    kind, field, before, after, detail = event.event_type, event.field, event.value_before, event.value_after, event.detail or {}
    if kind == "state_changed":
        return f"{_value(field, before)} -> {_value(field, after)}"
    if kind == "printwatch_command":
        verb = {"pause": "pausar", "resume": "reanudar", "cancel": "cancelar"}.get(detail.get("action"), detail.get("action") or "")
        who = "pausa automática por spaghetti" if detail.get("source") == "auto_pause" else detail.get("requested_by") or "web"
        if detail.get("followup"):
            return f"La orden de {verb} ({who}) no se completó: {detail.get('error') or 'sin detalle'}"
        failed = f" (falló: {detail.get('error') or 'sin detalle'})" if detail.get("ok") is False else ""
        return f"Pidió {verb} ({who}){failed}"
    if kind in ("object_excluded", "console_command", "gcode_error"):
        return str(after)
    if kind == "monitor_connected":
        return f"Estado al conectar: {_value('print_stats.state', after)}"
    if kind == "monitor_disconnected":
        return str(detail.get("reason") or "")
    if field:
        return f"{_field_name(field)}: {_value(field, before)} -> {_value(field, after)}"
    return ""


class _Report(FPDF):
    def __init__(self, title: str) -> None:
        super().__init__(orientation="P", unit="mm", format="A4")
        self.report_title = title
        self.set_margins(15, 14, 15)
        self.set_auto_page_break(True, margin=16)
        self.set_title(_t(title))
        self.set_author("PrintWatch")
        self.set_creator("PrintWatch")

    def header(self) -> None:
        if self.page_no() == 1:
            return
        self.set_font("Helvetica", "", 8)
        self.set_text_color(*FAINT)
        self.cell(0, 5, _t(self.report_title), align="R", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.ln(2)

    def footer(self) -> None:
        self.set_y(-12)
        self.set_font("Helvetica", "", 8)
        self.set_text_color(*FAINT)
        self.cell(0, 5, _t(f"PrintWatch · página {self.page_no()} de {{nb}}"), align="C")

    @property
    def content_width(self) -> float:
        return self.w - self.l_margin - self.r_margin

    def heading(self, text: str) -> None:
        if self.get_y() > self.h - 40:
            self.add_page()
        self.ln(3)
        self.set_font("Helvetica", "B", 12)
        self.set_text_color(*INK)
        self.cell(0, 7, _t(text), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.set_draw_color(*LINE)
        self.set_line_width(0.3)
        self.line(self.l_margin, self.get_y(), self.w - self.r_margin, self.get_y())
        self.ln(2.5)

    def paragraph(self, text: str, size: float = 9, color=MUTED) -> None:
        self.set_font("Helvetica", "", size)
        self.set_text_color(*color)
        self.multi_cell(0, size * 0.48, _t(text), new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    def facts(self, rows: list[tuple[str, str]], label_width: float = 58) -> None:
        for label, value in rows:
            self.set_font("Helvetica", "", 9.5)
            self.set_text_color(*MUTED)
            self.cell(label_width, 5.6, _t(label))
            self.set_text_color(*INK)
            self.multi_cell(self.content_width - label_width, 5.6, _t(value), new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    def data_table(self, headings: list[str], widths: tuple, rows: list[list[str]], size: float = 8) -> None:
        self.set_font("Helvetica", "", size)
        # The table takes the current colors as its cells' style: white background, dark text.
        self.set_text_color(*INK)
        self.set_fill_color(255, 255, 255)
        self.set_draw_color(*LINE)
        self.set_line_width(0.2)
        with self.table(
            col_widths=widths,
            line_height=size * 0.55,
            headings_style=FontFace(emphasis=TextEmphasis.B, color=INK, fill_color=LIGHT),
            borders_layout="HORIZONTAL_LINES",
            text_align="LEFT",
        ) as table:
            heading_row = table.row()
            for heading in headings:
                heading_row.cell(_t(heading))
            for values in rows:
                row = table.row()
                for value in values:
                    row.cell(_t(value))


def _nice_step(span: float, ticks: int) -> float:
    raw = span / max(ticks, 1)
    if raw <= 0:
        return 1.0
    magnitude = 10 ** math.floor(math.log10(raw))
    return next(multiple * magnitude for multiple in (1, 2, 2.5, 5, 10) if multiple * magnitude >= raw)


_TIME_STEPS = (5, 10, 15, 30, 60, 120, 300, 600, 900, 1800, 3600, 7200, 10800, 21600, 43200, 86400)


def _time_ticks(start: datetime, end: datetime, max_ticks: int) -> tuple[list[datetime], int]:
    span = (end - start).total_seconds()
    step = next((step for step in _TIME_STEPS if span / step <= max_ticks), _TIME_STEPS[-1])
    local_start = start.astimezone(BOGOTA)
    midnight = local_start.replace(hour=0, minute=0, second=0, microsecond=0)
    first = midnight + timedelta(seconds=math.ceil((local_start - midnight).total_seconds() / step) * step)
    ticks, tick = [], first
    while tick <= end:
        ticks.append(tick)
        tick += timedelta(seconds=step)
    return ticks, step


def _time_chart(pdf: _Report, top: float, height: float, start: datetime, end: datetime, series: list[dict], unit: str,
                markers: list[tuple[datetime, tuple]], include: tuple[float, ...] = ()) -> None:
    """Lines over time, with a legend above and vertical markers (defects, interventions).
    `include`: values the axis must cover even when the data doesn't (so a flat 100 % line has room)."""
    left, width = pdf.l_margin, pdf.content_width
    values = [value for spec in series for _, value in spec["points"] if value is not None]
    if values:
        values += list(include)
    pdf.set_font("Helvetica", "", 7.5)
    legend_x = left + 13
    for spec in series:
        pdf.set_draw_color(*spec["color"])
        pdf.set_line_width(0.6)
        if spec.get("dashed"):
            pdf.set_dash_pattern(dash=1.2, gap=0.8)
        pdf.line(legend_x, top + 2, legend_x + 6, top + 2)
        pdf.set_dash_pattern()
        pdf.set_text_color(*MUTED)
        pdf.set_xy(legend_x + 7, top)
        label = _t(spec["label"])
        pdf.cell(pdf.get_string_width(label) + 1, 4, label)
        legend_x += 7 + pdf.get_string_width(label) + 5
    plot_left, plot_top = left + 13, top + 6
    plot_width, plot_height = width - 13, height - 12
    plot_bottom = plot_top + plot_height
    if not values or end <= start:
        pdf.set_xy(plot_left, plot_top + plot_height / 2 - 2)
        pdf.set_text_color(*FAINT)
        pdf.cell(plot_width, 4, _t("Sin telemetría para este trabajo."), align="C")
        pdf.set_y(top + height)
        return

    low, high = min(values), max(values)
    step = _nice_step(max(high - low, 1e-6), 4)
    low, high = math.floor(low / step) * step, math.ceil(high / step) * step
    if high <= low:
        high = low + step
    span = (end - start).total_seconds()

    def x_of(moment: datetime) -> float:
        return plot_left + (moment - start).total_seconds() / span * plot_width

    def y_of(value: float) -> float:
        return plot_bottom - (value - low) / (high - low) * plot_height

    pdf.set_line_width(0.15)
    pdf.set_draw_color(*LINE)
    pdf.set_font("Helvetica", "", 7)
    pdf.set_text_color(*FAINT)
    tick = low
    while tick <= high + step / 2:
        pdf.line(plot_left, y_of(tick), plot_left + plot_width, y_of(tick))
        pdf.set_xy(left, y_of(tick) - 1.8)
        pdf.cell(12, 3.6, _t(f"{_num(tick, 0 if step >= 1 else 1)}"), align="R")
        tick += step

    ticks, time_step = _time_ticks(start, end, max(2, int(plot_width // 22)))
    for moment in ticks:
        pdf.set_xy(x_of(moment) - 10, plot_bottom + 1)
        pdf.cell(20, 3.6, moment.astimezone(BOGOTA).strftime("%H:%M:%S" if time_step < 60 else "%H:%M"), align="C")
    pdf.set_xy(plot_left + plot_width - 30, plot_bottom + 4.2)
    pdf.cell(30, 3.6, _t(f"hora de Colombia · {unit}"), align="R")

    pdf.set_line_width(0.25)
    for moment, color in markers:
        if start <= moment <= end:
            pdf.set_draw_color(*color)
            pdf.set_dash_pattern(dash=0.8, gap=0.8)
            pdf.line(x_of(moment), plot_top, x_of(moment), plot_bottom)
    pdf.set_dash_pattern()

    for spec in series:
        pdf.set_draw_color(*spec["color"])
        pdf.set_line_width(0.45 if not spec.get("dashed") else 0.35)
        if spec.get("dashed"):
            pdf.set_dash_pattern(dash=1.2, gap=0.8)
        segment: list[tuple[float, float]] = []
        for moment, value in spec["points"] + [(None, None)]:
            if value is None or moment is None:
                if len(segment) > 1:
                    pdf.polyline(segment)
                segment = []
                continue
            segment.append((x_of(moment), y_of(min(max(value, low), high))))
        pdf.set_dash_pattern()
    pdf.set_y(top + height)


def _bed_map(pdf: _Report, top: float, size: float, geometry: dict | None, path: list, defects: list[dict]) -> None:
    """The bed from above (front at the bottom), with the parts, the head's path and the defects:
    reliable ones as a dot with the class code, the rest as a dashed circle the size of their error."""
    width, depth = defect_map.bed_dimensions(geometry)
    scale = size / max(width, depth)
    left = pdf.l_margin + 8

    def x_of(value: float) -> float:
        return left + value * scale

    def y_of(value: float) -> float:
        return top + (depth - value) * scale

    pdf.set_fill_color(*LIGHT)
    pdf.set_draw_color(*LINE)
    pdf.set_line_width(0.3)
    pdf.rect(left, top, width * scale, depth * scale, style="DF")
    pdf.set_font("Helvetica", "", 6.5)
    pdf.set_text_color(*FAINT)
    pdf.set_line_width(0.1)
    for value in range(0, int(max(width, depth)) + 1, 50):
        if value <= width:
            pdf.line(x_of(value), top, x_of(value), y_of(0))
            pdf.set_xy(x_of(value) - 5, y_of(0) + 0.8)
            pdf.cell(10, 3, str(value), align="C")
        if value <= depth:
            pdf.line(left, y_of(value), x_of(width), y_of(value))
            pdf.set_xy(left - 9, y_of(value) - 1.5)
            pdf.cell(8, 3, str(value), align="R")
    pdf.set_xy(left, top - 4)
    pdf.cell(width * scale, 3, _t("fondo"), align="C")
    pdf.set_xy(left, y_of(0) + 4)
    pdf.cell(width * scale, 3, _t("frente (mm)"), align="C")

    if path and len(path) > 1:
        step = max(1, math.ceil(len(path) / 800))
        pdf.set_draw_color(185, 192, 200)
        pdf.set_line_width(0.12)
        pdf.polyline([(x_of(x), y_of(y)) for x, y in path[::step]])

    pdf.set_line_width(0.3)
    for obj in (geometry or {}).get("objects") or []:
        polygon = obj.get("polygon") or []
        if len(polygon) > 2:
            pdf.set_draw_color(*BED)
            pdf.polyline([(x_of(x), y_of(y)) for x, y in polygon], polygon=True)
            if obj.get("center"):
                pdf.set_text_color(*BED)
                pdf.set_font("Helvetica", "", 6)
                pdf.set_xy(x_of(obj["center"][0]) - 10, y_of(obj["center"][1]) - 1.5)
                pdf.cell(20, 3, _t(obj.get("name") or ""), align="C")

    for defect in defects:
        color = CLASS_COLORS.get(defect["class_name"] or "", FAINT)
        cx, cy = x_of(defect["x"]), y_of(defect["y"])
        if defect["reliable"]:
            pdf.set_fill_color(*color)
            pdf.set_draw_color(*INK)
            pdf.set_line_width(0.15)
            pdf.circle(cx, cy, 1.5, style="DF")
        else:
            pdf.set_draw_color(*color)
            pdf.set_line_width(0.25)
            pdf.set_dash_pattern(dash=0.7, gap=0.7)
            pdf.circle(cx, cy, min(defect["uncertainty_mm"], 45) * scale)
            pdf.set_dash_pattern()
            pdf.set_fill_color(*color)
            pdf.circle(cx, cy, 0.6, style="F")
        pdf.set_font("Helvetica", "B", 5.5)
        pdf.set_text_color(*color)
        pdf.set_xy(cx - 4, cy - 4.2)
        pdf.cell(8, 2.5, CLASS_CODES.get(defect["class_name"] or "", "?"), align="C")

    legend_x = left + width * scale + 8
    pdf.set_xy(legend_x, top)
    pdf.set_font("Helvetica", "", 8)
    pdf.set_text_color(*MUTED)
    legend = [f"{code} = {CLASS_LABELS[name]}" for name, code in CLASS_CODES.items()]
    legend += ["", "Punto: ubicación confiable (error <= 20 mm).", "Círculo punteado: poco confiable; su radio es el error estimado.",
               "Línea gris: recorrido del cabezal.", "Azul: piezas declaradas en el archivo."]
    for line in legend:
        pdf.set_x(legend_x)
        pdf.multi_cell(pdf.w - pdf.r_margin - legend_x, 4.2, _t(line), new_x=XPos.LEFT, new_y=YPos.NEXT)
    pdf.set_y(top + depth * scale + 9)


async def _job_series(db: AsyncSession, job_id: int) -> list[dict]:
    columns = ("ts", *telemetry.SAMPLE_FIELDS)
    result = await db.execute(
        select(*[getattr(TelemetrySample, name) for name in columns])
        .where(TelemetrySample.print_job_id == job_id)
        .order_by(TelemetrySample.ts)
    )
    points = [{**dict(zip(columns, row)), "extra": None} for row in result.all()]
    thinned, _ = telemetry.downsample(points, MAX_CHART_POINTS)
    return thinned


async def build_report(db: AsyncSession, job: PrintJob) -> bytes:
    printer = await db.get(Printer, job.printer_id)
    summary = await timeline.get_job_summary(db, job.id)
    located, skipped = await defect_map.locate_job_defects(db, job)
    head_path = await defect_map.job_head_path(db, job.id)
    scores = await fusion.job_fusion(db, job)
    cost = await costs.job_cost(db, job)
    events = list(reversed(await printer_events.list_events(db, job.printer_id, job_id=job.id, limit=1000)))
    chain = await printer_events.verify_chain(db, job.printer_id)
    series = await _job_series(db, job.id)
    layer_times = {
        number: detected_at
        for number, detected_at in (await db.execute(select(Layer.layer_number, Layer.detected_at).where(Layer.job_id == job.id))).all()
    }
    alerts_total = await db.scalar(
        select(func.count(Alert.id))
        .join(Detection, Detection.id == Alert.detection_id)
        .join(LayerCapture, LayerCapture.id == Detection.capture_id)
        .join(Layer, Layer.id == LayerCapture.layer_id)
        .where(Layer.job_id == job.id)
    )
    synthetic = bool(
        await db.scalar(
            select(func.count(Detection.id))
            .join(LayerCapture, LayerCapture.id == Detection.capture_id)
            .join(Layer, Layer.id == LayerCapture.layer_id)
            .where(Layer.job_id == job.id, Detection.raw_output["synthetic"].as_boolean().is_(True))
        )
    )

    now = datetime.now(timezone.utc)
    end = job.ended_at or now
    file = telemetry.job_file_info(job.geometry, job.file_name) or {}
    # Klipper's own print clock at the last sample (kept in extra since 2026-10-08), when there is one.
    printed_s = await db.scalar(
        select(TelemetrySample.extra["print_stats.print_duration"].astext.cast(Float))
        .where(TelemetrySample.print_job_id == job.id, TelemetrySample.extra.is_not(None))
        .order_by(TelemetrySample.ts.desc())
        .limit(1)
    )
    first_progress = series[0].get("progress") if series else None
    mid_print = bool(series) and joined_late(series[0].get("layer_number"), first_progress)
    title = f"Reporte del trabajo #{job.id} · {job.file_name}"
    pdf = _Report(title)
    pdf.add_page()

    # --- Title and summary ---
    pdf.set_font("Helvetica", "B", 17)
    pdf.set_text_color(*INK)
    pdf.cell(0, 9, _t("Reporte de impresión"), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_font("Helvetica", "", 11)
    pdf.cell(0, 6, _t(f"Trabajo #{job.id} · {job.file_name}"), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.paragraph(
        f"{printer.name if printer else 'Impresora'} · {STATUS_LABELS.get(job.status.value, job.status.value)} · generado el "
        f"{_local(now, seconds=False)} (hora de Colombia) con los datos de ese momento."
        + (" El trabajo sigue en curso: el reporte es parcial." if job.status.value == "running" else "")
    )
    if synthetic:
        pdf.ln(1)
        pdf.paragraph("Modo demostración: las detecciones de este trabajo son sintéticas (no las hizo el modelo).", 9, PAUSE_MARK)
    pdf.ln(1)

    duration = (end - job.started_at).total_seconds()
    estimated_time = file.get("estimated_time")
    origin = "nombre del archivo" if file.get("estimated_time_source") == "filename" else "laminador"
    has_estimate = isinstance(estimated_time, (int, float)) and estimated_time > 0
    if printed_s is not None:
        # Klipper's clock covers the whole print even if PrintWatch joined it late.
        time_text = f"{_duration(printed_s)} imprimiendo (reloj de la impresora)"
        if has_estimate:
            difference = (printed_s - estimated_time) / estimated_time * 100
            time_text += f"; {origin}: {_duration(estimated_time)} ({'+' if difference >= 0 else ''}{_num(difference, 1)} %)"
    elif mid_print:
        time_text = f"{_duration(duration)} desde que PrintWatch lo siguió"
        if has_estimate:
            time_text += f" (la estimación de la pieza completa, según el {origin}, es {_duration(estimated_time)})"
    else:
        time_text = _duration(duration)
        if has_estimate:
            difference = (duration - estimated_time) / estimated_time * 100
            time_text += f" ({origin}: {_duration(estimated_time)}; {'+' if difference >= 0 else ''}{_num(difference, 0)} %)"
        else:
            time_text += " (no hay estimación del laminador para este archivo)"
    class_counts = ", ".join(
        f"{CLASS_LABELS.get(name, name)}: {count}" for name, count in sorted(summary["defect_class_counts"].items())
    ) or "ninguna"
    origins: dict[str, int] = {}
    for event in events:
        if event.event_type in INTERVENTION_TYPES and event.origin != "gcode_file":
            origins[event.origin] = origins.get(event.origin, 0) + 1
    interventions = ", ".join(f"{ORIGIN_LABELS.get(origin, origin)}: {count}" for origin, count in sorted(origins.items())) or "ninguna"
    auto_pauses = sum(1 for event in events if event.event_type == "printwatch_command" and (event.detail or {}).get("source") == "auto_pause")
    filament = cost["filament"]
    filament_text = "-"
    if filament["used_mm"] is not None:
        filament_text = f"{_num(filament['used_mm'] / 1000, 2)} m · {_grams(filament['used_g'])} g"
        if filament["estimated_mm"]:
            estimate = f"{_num(filament['estimated_mm'] / 1000, 2)} m"
            if filament["estimated_g"]:
                estimate += f" · {_grams(filament['estimated_g'])} g"
            filament_text += f" (laminador, archivo completo: {estimate})"
    energy = cost["energy"]
    currency = cost["currency"]
    pdf.facts([
        ("Inicio", _local(job.started_at)),
        ("Fin", _local(job.ended_at) if job.ended_at else "en curso"),
        ("Duración real", time_text),
        ("Capas", f"{summary['total_layers_recorded']} registradas"
                  + (f" de {job.estimated_layers}" if job.estimated_layers else "")
                  + f"; {summary['layers_captured']} con foto; {summary['layers_with_defect']} con defecto"),
        ("Clases detectadas (capas)", class_counts),
        ("Alertas", f"{alerts_total or 0} ({summary['active_alerts_count']} sin cerrar)"),
        ("Intervenciones", interventions + (f"; pausas automáticas: {auto_pauses}" if auto_pauses else "")),
        ("Filamento usado", filament_text + (f"; material {filament['material']}" if filament["material"] else "")),
        ("Energía de calentadores*", f"{_num(energy['total_kwh'], 3)} kWh (boquilla {_num(energy['extruder_wh'], 0)} Wh, "
                                     f"cama {_num(energy['bed_wh'], 0)} Wh)" if energy else "-"),
        ("Costo estimado*", f"{_money(cost['total_cost'], currency)} (filamento {_money(filament['cost'], currency)}, "
                            f"energía {_money(energy['cost'] if energy else None, currency)})"
                            + (" - precios de ejemplo, sin configurar" if cost["settings_are_default"] else "")),
    ])
    pdf.ln(1)
    pdf.paragraph("* Estimaciones; ver \"Cómo se calculan\" al final.", 7.5, FAINT)
    if mid_print:
        pdf.paragraph(
            f"PrintWatch se unió a esta impresión ya al {_num(first_progress * 100, 0)} % (capa {series[0].get('layer_number')}): las capas, la "
            "telemetría, las gráficas y la energía cuentan desde ahí. El filamento sí es el de toda la impresión (lo lleva la propia impresora).",
            8, MUTED,
        )

    # --- Charts ---
    pdf.heading("Telemetría")
    if series:
        start = series[0]["ts"]
        chart_end = max(series[-1]["ts"], start + timedelta(seconds=1))
        markers = [(layer_times[number], DEFECT_MARK) for number in sorted({item["layer_number"] for item in scores
                   if item["class_name"] not in INFORMATIONAL}) if number in layer_times]
        markers += [(event.ts, INTERVENTION_MARK) for event in events if event.event_type in INTERVENTION_TYPES and event.origin != "gcode_file"]
        markers += [(event.ts, PAUSE_MARK) for event in events if event.event_type == "state_changed" and event.value_after == "paused"]

        def points(key: str, factor: float = 1.0) -> list:
            return [(row["ts"], None if row.get(key) is None else row[key] * factor) for row in series]

        _time_chart(pdf, pdf.get_y(), 62, start, chart_end, [
            {"label": "Boquilla", "color": NOZZLE, "points": points("extruder_temp")},
            {"label": "Objetivo boquilla", "color": NOZZLE, "dashed": True, "points": points("extruder_target")},
            {"label": "Cama", "color": BED, "points": points("bed_temp")},
            {"label": "Objetivo cama", "color": BED, "dashed": True, "points": points("bed_target")},
        ], "°C", markers)
        pdf.ln(3)
        _time_chart(pdf, pdf.get_y(), 46, start, chart_end, [
            {"label": "Velocidad", "color": SPEED, "points": points("speed_factor", 100)},
            {"label": "Flujo", "color": FLOW, "points": points("extrude_factor", 100)},
            {"label": "Ventilador de capa", "color": FAN, "dashed": True, "points": points("fan_speed", 100)},
        ], "%", markers, include=(0, 110))
        pdf.ln(1)
        pdf.paragraph("Líneas verticales: naranja, capas con defecto; gris, intervenciones; roja, pausas.", 7.5, FAINT)
    else:
        pdf.paragraph("Este trabajo no tiene telemetría guardada (es anterior a esa función o la impresora no respondía).")

    # --- Bed map ---
    pdf.add_page()
    pdf.heading("Mapa de defectos en la cama")
    if located:
        _bed_map(pdf, pdf.get_y() + 5, 105, job.geometry, head_path, located)
    else:
        pdf.paragraph("Ningún defecto se pudo ubicar en la cama"
                      + (f" ({skipped} recuadros sin calibración de la cámara o en formato antiguo)." if skipped else "."))

    # --- Defects ---
    pdf.heading("Defectos detectados")
    by_box = {(item["detection_id"], item["box_index"]): item for item in located}
    if scores:
        rows = []
        for item in scores:
            place = by_box.get((item["detection_id"], item["box_index"]))
            position = "-" if place is None else f"({_num(place['x'], 0)}, {_num(place['y'], 0)}) ±{_num(place['uncertainty_mm'], 0)} mm" + (
                "" if place["reliable"] else " *")
            reasons = "; ".join(signal["label"].lower() for signal in item["signals"] if signal["met"]) or "-"
            rows.append([
                str(item["layer_number"]),
                CLASS_LABELS.get(item["class_name"] or "", item["class_name"] or "-"),
                f"{_num((item['confidence'] or 0) * 100, 0)} %",
                f"{_num(item['score'] * 100, 0)} %",
                position,
                (place or {}).get("object") or "-",
                reasons,
            ])
        pdf.data_table(["Capa", "Clase", "Modelo", "Combinado", "Posición en la cama", "Pieza", "Telemetría a favor"],
                       (9, 30, 13, 16, 34, 14, 44), rows)
        pdf.ln(1)
        pdf.paragraph("* Ubicación poco confiable (error estimado mayor a 20 mm).", 7.5, FAINT)
    else:
        pdf.paragraph("El modelo no marcó defectos en este trabajo.")

    # --- Event log ---
    pdf.heading("Bitácora del trabajo")
    if events:
        shown = events[:MAX_EVENT_ROWS]
        pdf.data_table(
            ["Hora", "Evento", "Cambio", "Origen"],
            (20, 38, 92, 30),
            [[event.ts.astimezone(BOGOTA).strftime("%H:%M:%S"), EVENT_LABELS.get(event.event_type, event.event_type),
              describe_event(event), ORIGIN_LABELS.get(event.origin, event.origin)] for event in shown],
        )
        if len(events) > len(shown):
            pdf.paragraph(f"Se muestran los primeros {len(shown)} de {len(events)} eventos; el resto está en la web.", 7.5, FAINT)
    else:
        pdf.paragraph("Sin eventos registrados para este trabajo.")

    # --- Integrity and method ---
    pdf.heading("Integridad de la bitácora")
    if chain["ok"]:
        pdf.paragraph(
            f"Al generar este reporte, la cadena de eventos de la impresora estaba íntegra ({chain['events_checked']} eventos "
            f"verificados). Hash del último evento:", 9, INK)
        pdf.set_font("Courier", "", 8.5)
        pdf.set_text_color(*INK)
        pdf.cell(0, 5, chain["last_hash"] or "-", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.paragraph("Guardar este reporte permite comprobar después que nadie borró ni reescribió eventos: ese hash debe seguir "
                      "apareciendo en la cadena.", 8, MUTED)
    else:
        pdf.paragraph(f"La cadena de eventos de la impresora está rota desde el evento {chain['first_broken_id']} "
                      f"({chain['reason']}): algún evento se editó o borró después de registrarse.", 9, PAUSE_MARK)

    settings = cost["settings"]
    pdf.heading("Cómo se calculan las estimaciones")
    pdf.paragraph(
        "Filamento: lo que la impresora mandó extruir (print_stats.filament_used), no un pesaje. Los gramos salen de los gramos por "
        "milímetro del laminador cuando el archivo los trae; si no, de la densidad típica del material "
        f"({_num(settings['filament_diameter_mm'], 2)} mm de diámetro)."
    )
    pdf.paragraph(
        "Energía: solo los dos calentadores, como su PWM en cada segundo por su potencia nominal "
        f"(boquilla {_num(settings['extruder_heater_w'], 0)} W, cama {_num(settings['bed_heater_w'], 0)} W). No incluye motores, "
        "ventiladores, electrónica ni pantalla. Precios: "
        f"{_money(settings['filament_price_per_kg'], currency)} por kg y {_money(settings['energy_price_per_kwh'], currency)} por kWh."
    )
    pdf.paragraph(
        "Puntaje combinado: 1 - (1 - confianza del modelo) x producto de (1 - peso) de cada señal de telemetría cumplida en la capa "
        "recién impresa (pesos iniciales 0,6 / 0,3 / 0,15, sin calibrar con impresiones reales). Es informativo: las alertas y la "
        "pausa automática usan solo el modelo."
    )
    pdf.paragraph(
        "Posición en la cama: homografía de la calibración de la cámara, corregida por el paralaje (altura de la capa) y el "
        "desplazamiento de la cama en Y; el error combina el marcado de las esquinas, el paralaje residual y el movimiento de la "
        "cama durante la foto."
    )
    return bytes(pdf.output())
