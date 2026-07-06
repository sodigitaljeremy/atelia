"""Accès données du module Conformité : ingestion idempotente + recherche vectorielle."""

import logging
from datetime import date

from app.core import db, llm
from app.modules.compliance import ingestion

logger = logging.getLogger(__name__)


async def upsert_document(meta: dict) -> int:
    async with db.pool.acquire() as conn:
        return await conn.fetchval(
            """
            INSERT INTO compliance_document (titre, source_celex, source_date, source_url)
            VALUES ($1, $2, $3, $4)
            ON CONFLICT (source_celex) DO UPDATE
                SET titre = excluded.titre, source_date = excluded.source_date,
                    source_url = excluded.source_url
            RETURNING id
            """,
            meta["titre"],
            meta["source_celex"],
            date.fromisoformat(meta["source_date"]) if meta.get("source_date") else None,
            meta.get("source_url"),
        )


async def existing_refs(document_id: int) -> set[str]:
    async with db.pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT ref_article FROM compliance_chunk WHERE document_id = $1", document_id
        )
    return {row["ref_article"] for row in rows}


async def insert_chunks(document_id: int, chunks: list[dict], vectors: list[list[float]]) -> None:
    async with db.pool.acquire() as conn:
        await conn.executemany(
            """
            INSERT INTO compliance_chunk (document_id, ref_article, contenu, embedding)
            VALUES ($1, $2, $3, $4::vector)
            ON CONFLICT (document_id, ref_article) DO NOTHING
            """,
            [
                (document_id, chunk["ref_article"], chunk["contenu"], ingestion.to_pgvector(vec))
                for chunk, vec in zip(chunks, vectors)
            ],
        )


async def ingest_corpus() -> dict:
    """Ingestion idempotente : seuls les chunks ABSENTS sont vectorisés (aucun appel
    d'embedding inutile) puis insérés. Relançable à volonté sans doublon (UNIQUE)."""
    report = {"documents": 0, "chunks_added": 0, "chunks_skipped": 0}
    for document in ingestion.load_corpus():
        document_id = await upsert_document(document["meta"])
        report["documents"] += 1
        known = await existing_refs(document_id)
        missing = [c for c in document["chunks"] if c["ref_article"] not in known]
        report["chunks_skipped"] += len(document["chunks"]) - len(missing)
        if not missing:
            continue
        embeddings = await llm.embed_many([c["contenu"] for c in missing])
        await insert_chunks(document_id, missing, embeddings["vectors"])
        report["chunks_added"] += len(missing)
    return report


async def ingest_corpus_best_effort() -> None:
    """Hook de démarrage : la prod s'auto-indexe, mais une panne LLM ne bloque pas l'app."""
    try:
        report = await ingest_corpus()
        logger.info("Ingestion corpus conformité : %s", report)
    except Exception:
        logger.warning(
            "Ingestion du corpus conformité impossible au démarrage — "
            "relancer scripts/ingest_compliance.py",
            exc_info=True,
        )


async def corpus_status() -> list[dict]:
    async with db.pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT d.titre, d.source_celex, d.source_date, d.source_url,
                   count(c.id) AS chunks
            FROM compliance_document d
            LEFT JOIN compliance_chunk c ON c.document_id = d.id
            GROUP BY d.id ORDER BY d.id
            """
        )
    return [dict(row) for row in rows]


async def search_chunks(query: str, limit: int = 5) -> list[dict]:
    """Recherche sémantique : vectorise LA REQUÊTE seulement, distance cosinus pgvector.

    Similarité affichée = 1 - distance cosinus (1 = identique, 0 = orthogonal).
    """
    embeddings = await llm.embed_many([query])
    vector = ingestion.to_pgvector(embeddings["vectors"][0])
    async with db.pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT c.ref_article, c.contenu, d.titre, d.source_celex,
                   1 - (c.embedding <=> $1::vector) AS similarite
            FROM compliance_chunk c
            JOIN compliance_document d ON d.id = c.document_id
            ORDER BY c.embedding <=> $1::vector
            LIMIT $2
            """,
            vector,
            limit,
        )
    return [dict(row) for row in rows]
