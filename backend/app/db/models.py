import enum
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    REAL,
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Double,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ENUM as PGEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class UserRole(str, enum.Enum):
    admin = "admin"
    viewer = "viewer"


class IntegrationType(str, enum.Enum):
    octoprint = "octoprint"
    moonraker = "moonraker"


class PrinterStatus(str, enum.Enum):
    idle = "idle"
    printing = "printing"
    paused = "paused"
    error = "error"
    offline = "offline"


class CameraSourceType(str, enum.Enum):
    usb = "usb"
    rtsp = "rtsp"
    mjpeg_http = "mjpeg_http"


class CameraRole(str, enum.Enum):
    primary = "primary"
    secondary = "secondary"


class JobStatus(str, enum.Enum):
    running = "running"
    completed = "completed"
    failed = "failed"
    cancelled = "cancelled"


class AlertSeverity(str, enum.Enum):
    warning = "warning"
    critical = "critical"


class AlertStatus(str, enum.Enum):
    new = "new"
    acknowledged = "acknowledged"
    dismissed = "dismissed"
    false_positive = "false_positive"


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[UserRole] = mapped_column(
        PGEnum(UserRole, name="user_role"), default=UserRole.viewer, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Printer(Base):
    __tablename__ = "printers"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    model: Mapped[str | None] = mapped_column(String(100))
    # Names kept from the OctoPrint-only era: for a Moonraker printer these hold its base
    # URL (http://host:7125) and an empty key, since Moonraker needs no key on the LAN.
    octoprint_url: Mapped[str] = mapped_column(String(255), nullable=False)
    octoprint_api_key_encrypted: Mapped[str] = mapped_column(String(255), nullable=False)
    integration_type: Mapped[IntegrationType] = mapped_column(
        PGEnum(IntegrationType, name="integration_type"), default=IntegrationType.octoprint, nullable=False
    )
    last_known_status: Mapped[PrinterStatus] = mapped_column(
        PGEnum(PrinterStatus, name="printer_status"), default=PrinterStatus.offline, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    cameras: Mapped[list["Camera"]] = relationship(back_populates="printer", cascade="all, delete-orphan")
    print_jobs: Mapped[list["PrintJob"]] = relationship(back_populates="printer", cascade="all, delete-orphan")


class Camera(Base):
    __tablename__ = "cameras"
    __table_args__ = (UniqueConstraint("printer_id", "role", name="uq_camera_printer_role"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    printer_id: Mapped[int] = mapped_column(ForeignKey("printers.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    source_type: Mapped[CameraSourceType] = mapped_column(
        PGEnum(CameraSourceType, name="camera_source_type"), nullable=False
    )
    source_uri: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[CameraRole] = mapped_column(
        PGEnum(CameraRole, name="camera_role"), default=CameraRole.primary, nullable=False
    )
    roi: Mapped[dict | None] = mapped_column(JSONB)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    printer: Mapped["Printer"] = relationship(back_populates="cameras")
    layer_captures: Mapped[list["LayerCapture"]] = relationship(back_populates="camera")


class PrintJob(Base):
    __tablename__ = "print_jobs"

    id: Mapped[int] = mapped_column(primary_key=True)
    printer_id: Mapped[int] = mapped_column(ForeignKey("printers.id", ondelete="CASCADE"), nullable=False)
    octoprint_job_id: Mapped[str | None] = mapped_column(String(100))
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[JobStatus] = mapped_column(
        PGEnum(JobStatus, name="job_status"), default=JobStatus.running, nullable=False
    )
    estimated_layers: Mapped[int | None] = mapped_column(Integer)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # The bed as it was for this print: axis limits, bed mesh and the objects the file declared
    # (exclude_object), so its bed map can be drawn later even if the printer changes.
    geometry: Mapped[dict | None] = mapped_column(JSONB)

    printer: Mapped["Printer"] = relationship(back_populates="print_jobs")
    layers: Mapped[list["Layer"]] = relationship(back_populates="job", cascade="all, delete-orphan")


class Layer(Base):
    __tablename__ = "layers"
    __table_args__ = (UniqueConstraint("job_id", "layer_number", name="uq_layer_job_number"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("print_jobs.id", ondelete="CASCADE"), nullable=False)
    layer_number: Mapped[int] = mapped_column(Integer, nullable=False)
    z_height: Mapped[Decimal] = mapped_column(Numeric(6, 2), nullable=False)
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    # What the printer was doing when the layer started (temperatures, factors, head position,
    # object being printed), so a defect can be read next to the conditions that produced it.
    telemetry: Mapped[dict | None] = mapped_column(JSONB)

    job: Mapped["PrintJob"] = relationship(back_populates="layers")
    captures: Mapped[list["LayerCapture"]] = relationship(back_populates="layer", cascade="all, delete-orphan")


class LayerCapture(Base):
    __tablename__ = "layer_captures"
    __table_args__ = (UniqueConstraint("layer_id", "camera_id", name="uq_capture_layer_camera"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    layer_id: Mapped[int] = mapped_column(ForeignKey("layers.id", ondelete="CASCADE"), nullable=False)
    camera_id: Mapped[int] = mapped_column(ForeignKey("cameras.id", ondelete="CASCADE"), nullable=False)
    image_path: Mapped[str] = mapped_column(String(500), nullable=False)
    dominant_color_rgb: Mapped[str | None] = mapped_column(String(7))
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    layer: Mapped["Layer"] = relationship(back_populates="captures")
    camera: Mapped["Camera"] = relationship(back_populates="layer_captures")
    detections: Mapped[list["Detection"]] = relationship(back_populates="capture", cascade="all, delete-orphan")


class ModelVersion(Base):
    __tablename__ = "model_versions"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    file_path: Mapped[str] = mapped_column(String(500), nullable=False)
    classes: Mapped[list] = mapped_column(JSONB, nullable=False)
    metrics: Mapped[dict | None] = mapped_column(JSONB)
    trained_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    detections: Mapped[list["Detection"]] = relationship(back_populates="model_version")


class Detection(Base):
    __tablename__ = "detections"
    __table_args__ = (
        Index("ix_detections_has_defect_true", "has_defect", postgresql_where=text("has_defect = true")),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    capture_id: Mapped[int] = mapped_column(ForeignKey("layer_captures.id", ondelete="CASCADE"), nullable=False)
    model_version_id: Mapped[int] = mapped_column(ForeignKey("model_versions.id"), nullable=False)
    has_defect: Mapped[bool] = mapped_column(Boolean, nullable=False)
    max_confidence: Mapped[Decimal | None] = mapped_column(Numeric(4, 3))
    defect_classes: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    raw_output: Mapped[dict] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    capture: Mapped["LayerCapture"] = relationship(back_populates="detections")
    model_version: Mapped["ModelVersion"] = relationship(back_populates="detections")
    alerts: Mapped[list["Alert"]] = relationship(back_populates="detection", cascade="all, delete-orphan")


class Alert(Base):
    __tablename__ = "alerts"

    id: Mapped[int] = mapped_column(primary_key=True)
    detection_id: Mapped[int] = mapped_column(ForeignKey("detections.id", ondelete="CASCADE"), nullable=False)
    printer_id: Mapped[int] = mapped_column(ForeignKey("printers.id", ondelete="CASCADE"), nullable=False)
    severity: Mapped[AlertSeverity] = mapped_column(PGEnum(AlertSeverity, name="alert_severity"), nullable=False)
    status: Mapped[AlertStatus] = mapped_column(
        PGEnum(AlertStatus, name="alert_status"), default=AlertStatus.new, nullable=False
    )
    acknowledged_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    detection: Mapped["Detection"] = relationship(back_populates="alerts")


class CameraCalibration(Base):
    """Where a camera sees the bed, from four points marked on one of its frames. A new row per
    calibration: a detection is mapped with the calibration that was current when it was captured,
    so moving the camera later doesn't rewrite where past defects were."""

    __tablename__ = "camera_calibrations"
    __table_args__ = (Index("ix_camera_calibrations_camera_created", "camera_id", "created_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    camera_id: Mapped[int] = mapped_column(ForeignKey("cameras.id", ondelete="CASCADE"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    # Normalized (0..1) points on the frame, and the bed points (mm) they correspond to, in order.
    image_points: Mapped[list] = mapped_column(JSONB, nullable=False)
    bed_points: Mapped[list] = mapped_column(JSONB, nullable=False)
    image_width: Mapped[int] = mapped_column(Integer, nullable=False)
    image_height: Mapped[int] = mapped_column(Integer, nullable=False)
    # True for a camera fixed to the frame or table of a bed-slinger: the bed slides along Y in
    # the image, and reference_y (toolhead Y when the frame was taken) anchors that shift.
    bed_moves_in_image: Mapped[bool] = mapped_column(Boolean, nullable=False)
    reference_y: Mapped[float | None] = mapped_column(REAL)
    # Derived when calibrating, kept for display and auditing (app/services/bed_map.py).
    focal_px: Mapped[float | None] = mapped_column(REAL)
    camera_position: Mapped[list | None] = mapped_column(JSONB)


class TelemetrySample(Base):
    """The printer's state once per second while a print job is open. REAL (4 bytes, ~7
    significant digits) is plenty for sensor readings and halves the row against DOUBLE."""

    __tablename__ = "telemetry_samples"
    __table_args__ = (Index("ix_telemetry_samples_job_ts", "print_job_id", "ts"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    print_job_id: Mapped[int] = mapped_column(ForeignKey("print_jobs.id", ondelete="CASCADE"), nullable=False)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    # Klipper's monotonic clock at the last status update, to line samples up with klippy.log.
    klipper_eventtime: Mapped[float | None] = mapped_column(Double)
    layer_number: Mapped[int | None] = mapped_column(Integer)
    x: Mapped[float | None] = mapped_column(REAL)
    y: Mapped[float | None] = mapped_column(REAL)
    z: Mapped[float | None] = mapped_column(REAL)
    velocity: Mapped[float | None] = mapped_column(REAL)
    extruder_velocity: Mapped[float | None] = mapped_column(REAL)
    extruder_temp: Mapped[float | None] = mapped_column(REAL)
    extruder_target: Mapped[float | None] = mapped_column(REAL)
    extruder_power: Mapped[float | None] = mapped_column(REAL)
    bed_temp: Mapped[float | None] = mapped_column(REAL)
    bed_target: Mapped[float | None] = mapped_column(REAL)
    bed_power: Mapped[float | None] = mapped_column(REAL)
    fan_speed: Mapped[float | None] = mapped_column(REAL)
    speed_factor: Mapped[float | None] = mapped_column(REAL)
    extrude_factor: Mapped[float | None] = mapped_column(REAL)
    z_offset: Mapped[float | None] = mapped_column(REAL)
    progress: Mapped[float | None] = mapped_column(REAL)
    filament_used: Mapped[float | None] = mapped_column(REAL)
    # Sensors and fans that only some printers have, keyed by Klipper object and field.
    extra: Mapped[dict | None] = mapped_column(JSONB)


class PrinterEvent(Base):
    """Event log of a printer: state changes and interventions, each with who caused it.
    Rows form one hash chain per printer (hash covers the previous row's hash), so editing or
    deleting a row afterwards is detectable - see app/services/printer_events.py."""

    __tablename__ = "printer_events"
    __table_args__ = (
        Index("ix_printer_events_printer_id_id", "printer_id", "id"),
        Index("ix_printer_events_print_job_id", "print_job_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    printer_id: Mapped[int] = mapped_column(ForeignKey("printers.id", ondelete="CASCADE"), nullable=False)
    print_job_id: Mapped[int | None] = mapped_column(ForeignKey("print_jobs.id", ondelete="SET NULL"))
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    klipper_eventtime: Mapped[float | None] = mapped_column(Double)
    # Plain strings, not Postgres enums: new kinds of events must not need a migration.
    event_type: Mapped[str] = mapped_column(String(40), nullable=False)
    field: Mapped[str | None] = mapped_column(String(120))
    value_before: Mapped[Any] = mapped_column(JSONB, nullable=True)
    value_after: Mapped[Any] = mapped_column(JSONB, nullable=True)
    origin: Mapped[str] = mapped_column(String(20), nullable=False)
    detail: Mapped[dict | None] = mapped_column(JSONB)
    prev_hash: Mapped[str | None] = mapped_column(String(64))
    hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)


class Incident(Base):
    """One incident of a print: the model saw something that calls for a decision (or the print was paused),
    with the evidence, what PrintWatch did, what the user decided and, afterwards, whether it was right.

    Plain strings with CHECK constraints, not Postgres enums: a new status must not need an enum migration.
    reason  : why it was opened - would_pause (warn mode streak), auto_pause (on mode countdown), pause (the print
              was paused, by anyone) or detection (a detection of an eligible class over the threshold).
    status  : open, paused (Klipper confirmed it), unconfirmed (the pause was sent and Klipper did not confirm
              within 20 s, or could not be sent), closed.
    outcome : how it ended - resumed, cancelled, ignored (countdown aborted, dismissed or the job ended with
              nobody acting) or error (Klipper ended in error).
    label   : the user's verdict, to measure the false positive rate: correct, false_positive, unlabeled.
    Only one incident per job and class stays unclosed (partial unique index)."""

    __tablename__ = "incidents"
    __table_args__ = (
        Index("ix_incidents_printer_opened", "printer_id", "opened_at"),
        Index("ix_incidents_print_job_id", "print_job_id"),
        Index(
            "uq_incidents_open_job_class", "print_job_id", "defect_class", unique=True,
            postgresql_where=text("status <> 'closed'"),
        ),
        CheckConstraint("reason in ('would_pause', 'auto_pause', 'pause', 'detection')", name="ck_incidents_reason"),
        CheckConstraint("status in ('open', 'paused', 'unconfirmed', 'closed')", name="ck_incidents_status"),
        CheckConstraint("outcome is null or outcome in ('resumed', 'cancelled', 'ignored', 'error')", name="ck_incidents_outcome"),
        CheckConstraint("label in ('unlabeled', 'correct', 'false_positive')", name="ck_incidents_label"),
        CheckConstraint("mode is null or mode in ('on', 'warn')", name="ck_incidents_mode"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    print_job_id: Mapped[int] = mapped_column(ForeignKey("print_jobs.id", ondelete="CASCADE"), nullable=False)
    printer_id: Mapped[int] = mapped_column(ForeignKey("printers.id", ondelete="CASCADE"), nullable=False)
    camera_id: Mapped[int | None] = mapped_column(ForeignKey("cameras.id", ondelete="SET NULL"))
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    reason: Mapped[str] = mapped_column(String(20), nullable=False)
    mode: Mapped[str | None] = mapped_column(String(8))  # AUTO_PAUSE_MODE when it opened (null for a plain pause)
    defect_class: Mapped[str] = mapped_column(String(40), nullable=False)  # "pausa" for a pause with no detection
    # The layers of the streak, oldest first: layer, detection_id, capture_id, confidence, captured_at.
    streak: Mapped[list] = mapped_column(JSONB, nullable=False, server_default=text("'[]'::jsonb"))
    detection_id: Mapped[int | None] = mapped_column(ForeignKey("detections.id", ondelete="SET NULL"))
    first_defect_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))  # first photo with the defect
    announced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))  # the warning / the countdown start
    pause_sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    paused_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))  # Klipper reported "paused"
    status: Mapped[str] = mapped_column(String(12), nullable=False, server_default=text("'open'"))
    outcome: Mapped[str | None] = mapped_column(String(12))
    decided_by: Mapped[str | None] = mapped_column(String(100))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    label: Mapped[str] = mapped_column(String(14), nullable=False, server_default=text("'unlabeled'"))
    labeled_by: Mapped[str | None] = mapped_column(String(100))
    labeled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # The printer at the moment it opened: the job's latest telemetry sample and the layer's telemetry row.
    telemetry_snapshot: Mapped[dict | None] = mapped_column(JSONB)
    detail: Mapped[dict | None] = mapped_column(JSONB)  # triggers, pause origin, abort, send errors...
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class AppSetting(Base):
    """Settings the team edits from the web, one JSON value per key (for now "costs": the prices
    and heater wattages of the cost estimate)."""

    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[dict] = mapped_column(JSONB, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
