# ── Database Setup ────────────────────────────────────────────────────────────
# Async SQLAlchemy engine + session factory using asyncpg driver.

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.config import settings

# ── Engine ────────────────────────────────────────────────────────────────────
engine = create_async_engine(
    settings.DATABASE_URL,
    echo=False,  # Set True for SQL debug logging
    pool_size=20,
    max_overflow=10,
    pool_pre_ping=True,  # Verify connections before using them
)

# ── Session Factory ───────────────────────────────────────────────────────────
AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,  # Keep objects usable after commit
)


# ── Declarative Base ──────────────────────────────────────────────────────────
class Base(DeclarativeBase):
    """Base class for all ORM models."""

    pass


# ── Dependency: get a DB session ──────────────────────────────────────────────
async def get_db() -> AsyncSession:  # type: ignore[valid-type]
    """FastAPI dependency that yields an async database session."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
