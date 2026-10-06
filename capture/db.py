from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from capture.config import settings

# Writes directly to Postgres, same as the inference worker will - capture must not
# depend on the backend API being up to do its job.
engine = create_async_engine(settings.database_url, pool_pre_ping=True)
async_session_factory = async_sessionmaker(engine, expire_on_commit=False)
