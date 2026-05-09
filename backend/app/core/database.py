"""
Database configuration and async SQLAlchemy setup for the Dubai/UAE
real estate lead intelligence system.

TODO:
- Review and adjust connection settings (pool sizes, timeouts) for production.
- Wire this session dependency into FastAPI route handlers.
"""

from __future__ import annotations

import os
from typing import Any, AsyncGenerator

from sqlalchemy.engine.url import make_url
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import declarative_base

from .config import get_settings


# Base ORM class to be used across the application
Base = declarative_base()


def _normalize_database_url(raw_url: str) -> str:
    """
    Normalize the database URL for async SQLAlchemy + asyncpg.

    Supports:
    - postgresql+asyncpg://... (used as-is)
    - postgresql://... (e.g. Neon copy-paste) — converted to postgresql+asyncpg://
    """
    db_url = raw_url.strip()
    if db_url.startswith("postgresql://") and "postgresql+asyncpg" not in db_url:
        db_url = db_url.replace("postgresql://", "postgresql+asyncpg://", 1)

    # Neon copy/paste URLs often contain libpq-style query params such as:
    # - sslmode=require
    # - channel_binding=require
    # SQLAlchemy's asyncpg dialect may forward these query keys as connect() kwargs, which
    # asyncpg does not accept. For Neon we drop *all* query parameters and rely on
    # connect_args={"ssl": True} instead.
    url_obj = make_url(db_url)
    if "neon.tech" in db_url:
        url_obj = url_obj.set(query={})
        db_url = url_obj.render_as_string(hide_password=False)
    elif url_obj.query:
        # For non-Neon URLs, remove common unsupported libpq keys while preserving any
        # driver-specific parameters you might intentionally pass.
        q = dict(url_obj.query)
        for key in ("sslmode", "ssl", "channel_binding"):
            q.pop(key, None)
        url_obj = url_obj.set(query=q)
        db_url = url_obj.render_as_string(hide_password=False)
    return db_url


def _engine_connect_args(url: str) -> dict[str, Any]:
    """SSL and other connect args (e.g. for Neon)."""
    args: dict[str, Any] = {}
    # Neon requires SSL; enable it when using a Neon host
    if "neon.tech" in url:
        args["ssl"] = True
    return args


settings = get_settings()
DATABASE_URL = _normalize_database_url(settings.database_url)

# Print first 50 chars for verification on startup/import.
print(f"DATABASE_URL (first 50 chars): {DATABASE_URL[:50]}")

# Safe connection diagnostics (no secret leakage).
# This helps debug InvalidPasswordError without printing the actual password.
try:
    import hashlib

    u = make_url(DATABASE_URL)
    user = u.username or ""
    host = u.host or ""
    dbname = (u.database or "") if hasattr(u, "database") else ""
    pwd = u.password or ""
    pwd_len = len(pwd)
    pwd_fp = hashlib.sha256(pwd.encode("utf-8")).hexdigest()[:12] if pwd else ""
    pwd_masked = (pwd[:2] + "***" + pwd[-2:]) if pwd_len >= 4 else ("***" if pwd else "")
    print(
        "DB_CONN (sanitized): "
        f"user={user!r} host={host!r} db={dbname!r} "
        f"password_len={pwd_len} password_masked={pwd_masked!r} password_fp_sha256_12={pwd_fp!r}"
    )
except Exception:
    # Never block app startup due to debug logging.
    pass


# Async SQLAlchemy engine with connection pool configuration
engine = create_async_engine(
    DATABASE_URL,
    echo=False,
    pool_pre_ping=True,
    pool_size=int(os.getenv("DB_POOL_SIZE", "5")),
    max_overflow=int(os.getenv("DB_MAX_OVERFLOW", "10")),
    connect_args=_engine_connect_args(DATABASE_URL),
)


# Async session factory
AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI dependency that provides an AsyncSession.

    Usage in routes:
        async def endpoint(db: AsyncSession = Depends(get_db)):
            ...
    """

    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            # Session context manager handles closing; this is here for clarity.
            await session.close()


__all__ = [
    "Base",
    "engine",
    "AsyncSessionLocal",
    "get_db",
]

