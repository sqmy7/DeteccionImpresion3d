"""Thin, intentionally duplicated subset of backend/app/db/models.py.

Unlike capture/ (which runs natively on the same checkout as backend/ and reuses
backend's models via a sys.path shim), this worker is a genuinely separate Docker
build context - infra/docker-compose.yml builds it from ../inference only, with no
access to ../backend at build/run time. That's a real packaging boundary, not just
a convenience split, so duplicating the minimal subset this process touches is the
more honest choice here. Only the columns actually read/written are declared.
If backend's schema changes for cameras/model_versions/detections, mirror it here.
"""

from decimal import Decimal

from sqlalchemy import Boolean, Integer, Numeric, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Camera(Base):
    __tablename__ = "cameras"

    id: Mapped[int] = mapped_column(primary_key=True)
    roi: Mapped[dict | None] = mapped_column(JSONB)


class ModelVersion(Base):
    __tablename__ = "model_versions"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    file_path: Mapped[str] = mapped_column(String(500), nullable=False)
    classes: Mapped[list] = mapped_column(JSONB, nullable=False)
    # none_as_null: a Python None must become SQL NULL, not the JSON literal 'null' (SQLAlchemy's
    # default for JSONB), or `WHERE metrics IS NULL` would silently skip rows with no metrics.
    metrics: Mapped[dict | None] = mapped_column(JSONB(none_as_null=True))


class Detection(Base):
    __tablename__ = "detections"

    # Plain Integer, not ForeignKey(...): the real FK constraint already exists in
    # Postgres (created by backend's Alembic migration) and is enforced there regardless.
    # Declaring it as a SQLAlchemy ForeignKey here would require the referenced table
    # (layer_captures) to also be declared under this worker's own Base/MetaData, which
    # it isn't - this thin model only declares what it actually reads/writes.
    id: Mapped[int] = mapped_column(primary_key=True)
    capture_id: Mapped[int] = mapped_column(Integer, nullable=False)
    model_version_id: Mapped[int] = mapped_column(Integer, nullable=False)
    has_defect: Mapped[bool] = mapped_column(Boolean, nullable=False)
    max_confidence: Mapped[Decimal | None] = mapped_column(Numeric(4, 3))
    defect_classes: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    raw_output: Mapped[dict] = mapped_column(JSONB, nullable=False)
