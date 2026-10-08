from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.session import get_db
from app.schemas.analytics import AnalyticsSummaryRead
from app.services.analytics import analytics_summary

router = APIRouter(prefix="/analytics", tags=["analytics"], dependencies=[Depends(get_current_user)])


@router.get("/summary", response_model=AnalyticsSummaryRead)
async def get_analytics_summary(
    printer_id: int | None = None,
    days: int | None = Query(default=None, ge=1, le=3650, description="only jobs started in the last N days"),
    db: AsyncSession = Depends(get_db),
) -> dict:
    now = datetime.now(timezone.utc)
    since = now - timedelta(days=days) if days else None
    return await analytics_summary(db, printer_id, since, now)
