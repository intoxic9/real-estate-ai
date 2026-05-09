"""
Core application configuration and environment loading.

This module is responsible for:
- Loading the `.env` file from the backend root.
- Exposing a validated `DATABASE_URL` for Neon (or other Postgres) usage.

The `.env` file is expected at:
    D:\\Project\\Dubai\\backend\\.env
resolved programmatically as:
    Path(__file__).resolve().parent.parent.parent / ".env"
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote

from dotenv import load_dotenv


BACKEND_ROOT = Path(__file__).resolve().parent.parent.parent
ENV_PATH = BACKEND_ROOT / ".env"

# Load environment variables from the backend .env file.
if ENV_PATH.exists():
    load_dotenv(ENV_PATH, override=True)
else:
    # Fail fast if the expected .env is missing; this is a production system.
    raise RuntimeError(f".env file not found at expected path: {ENV_PATH}")


@dataclass(frozen=True)
class Settings:
    database_url: str


# Groq API key split by task, with backwards-compatible fallback.
GROQ_API_KEY_CHAT = os.getenv("GROQ_API_KEY_CHAT")
GROQ_API_KEY_AGENTS = os.getenv("GROQ_API_KEY_AGENTS")
GROQ_API_KEY_SEARCH = os.getenv("GROQ_API_KEY_SEARCH")


def get_settings() -> Settings:
    """
    Build strongly-typed settings from environment variables.
    """

    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        # Allow constructing DATABASE_URL from Neon-style discrete PG* variables.
        # This keeps config ergonomic while still failing fast if nothing is provided.
        pghost = os.getenv("PGHOST")
        pgdatabase = os.getenv("PGDATABASE")
        pguser = os.getenv("PGUSER")
        pgpassword = os.getenv("PGPASSWORD")
        pgport = os.getenv("PGPORT", "5432")

        if all([pghost, pgdatabase, pguser, pgpassword, pgport]):
            # Narrow Optional[str] to str for static type checkers.
            assert pghost is not None
            assert pgdatabase is not None
            assert pguser is not None
            assert pgpassword is not None
            assert pgport is not None
            # URL-encode username/password safely.
            user_enc = quote(pguser, safe="")
            pass_enc = quote(pgpassword, safe="")
            db_url = f"postgresql+asyncpg://{user_enc}:{pass_enc}@{pghost}:{pgport}/{pgdatabase}"
            # Make it available to the rest of the app as if it were provided directly.
            os.environ["DATABASE_URL"] = db_url
        else:
            raise RuntimeError(
                "DATABASE_URL is not set and PGHOST/PGDATABASE/PGUSER/PGPASSWORD are incomplete."
            )

    return Settings(database_url=db_url)


__all__ = [
    "Settings",
    "get_settings",
    "BACKEND_ROOT",
    "ENV_PATH",
    "GROQ_API_KEY_CHAT",
    "GROQ_API_KEY_AGENTS",
    "GROQ_API_KEY_SEARCH",
]

