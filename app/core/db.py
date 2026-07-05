import asyncpg

from app.core import registry
from app.core.config import settings

pool: asyncpg.Pool | None = None


async def connect() -> None:
    """Ouvre le pool, active pgvector et applique le schéma (idempotent) de chaque module."""
    global pool
    pool = await asyncpg.create_pool(settings.database_url, min_size=1, max_size=5)
    async with pool.acquire() as conn:
        await conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
        for module in registry.modules:
            await conn.execute(module.schema_path.read_text())


async def disconnect() -> None:
    global pool
    if pool is not None:
        await pool.close()
        pool = None


async def health() -> dict:
    """Vérifie la connexion et la présence de l'extension vector."""
    if pool is None:
        return {"connected": False, "pgvector": False}
    async with pool.acquire() as conn:
        vector_version = await conn.fetchval(
            "SELECT extversion FROM pg_extension WHERE extname = 'vector'"
        )
    return {"connected": True, "pgvector": vector_version is not None}
