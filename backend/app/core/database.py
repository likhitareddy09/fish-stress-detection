from sqlalchemy.ext.asyncio import (
    create_async_engine,
    AsyncSession,
    async_sessionmaker,
)
from sqlalchemy.orm import DeclarativeBase
from app.core.config import settings


# Create the async database engine
engine = create_async_engine(
    settings.DATABASE_URL,
    echo=True,       # Prints all SQL queries to terminal — useful for debugging
    future=True,
)

# Session factory — use this to create DB sessions
AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


# Base class — all your models (Tank, SensorReading, etc.) will inherit from this
class Base(DeclarativeBase):
    pass


# Dependency — FastAPI calls this to get a DB session per request
async def get_db():
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()