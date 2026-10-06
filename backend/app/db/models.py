import enum
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    DateTime,
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
