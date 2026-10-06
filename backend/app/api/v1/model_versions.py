from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_admin
from app.db.models import ModelVersion
from app.db.session import get_db
from app.schemas.model_version import ModelVersionCreate, ModelVersionRead

router = APIRouter(prefix="/model-versions", tags=["model-versions"], dependencies=[Depends(get_current_user)])


@router.get("", response_model=list[ModelVersionRead])
async def list_model_versions(db: AsyncSession = Depends(get_db)) -> list[ModelVersion]:
    result = await db.execute(select(ModelVersion).order_by(ModelVersion.id))
    return list(result.scalars().all())


@router.post("", response_model=ModelVersionRead, status_code=status.HTTP_201_CREATED, dependencies=[Depends(require_admin)])
async def create_model_version(payload: ModelVersionCreate, db: AsyncSession = Depends(get_db)) -> ModelVersion:
    model_version = ModelVersion(**payload.model_dump())
    db.add(model_version)
    await db.commit()
    await db.refresh(model_version)
    return model_version


@router.get("/{model_version_id}", response_model=ModelVersionRead)
async def get_model_version(model_version_id: int, db: AsyncSession = Depends(get_db)) -> ModelVersion:
    model_version = await db.get(ModelVersion, model_version_id)
    if model_version is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Model version not found")
    return model_version
