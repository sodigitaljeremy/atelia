"""Accès données du module Conformité : ingestion idempotente + recherche vectorielle."""

import hashlib
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


def corpus_hash(chunks: list[dict]) -> str:
    """Empreinte du contenu chunké : change si le texte OU le nettoyage change."""
    digest = hashlib.sha256()
    for chunk in chunks:
        digest.update(chunk["ref_article"].encode())
        digest.update(chunk["contenu"].encode())
    return digest.hexdigest()


async def stored_hash(document_id: int) -> str | None:
    async with db.pool.acquire() as conn:
        return await conn.fetchval(
            "SELECT corpus_hash FROM compliance_document WHERE id = $1", document_id
        )


async def ingest_corpus() -> dict:
    """Ingestion idempotente par empreinte de contenu.

    Hash identique → no-op total (0 appel d'embedding). Hash différent (texte source
    OU pipeline de nettoyage modifié) → les chunks du document sont régénérés et
    ré-embeddés en bloc, puis l'empreinte est mise à jour. C'est ce qui permet à la
    prod de se ré-indexer seule au déploiement d'un nettoyage amélioré.
    """
    report = {"documents": 0, "regenerated": 0, "unchanged": 0, "chunks_added": 0}
    for document in ingestion.load_corpus():
        document_id = await upsert_document(document["meta"])
        report["documents"] += 1
        new_hash = corpus_hash(document["chunks"])
        if await stored_hash(document_id) == new_hash:
            report["unchanged"] += 1
            continue
        embeddings = await llm.embed_many([c["contenu"] for c in document["chunks"]])
        # Une seule transaction : delete + insert + hash. Le hash n'est posé QUE si
        # l'insertion a réussi — un échec laisse l'ancien état, régénéré au prochain run.
        async with db.pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute(
                    "DELETE FROM compliance_chunk WHERE document_id = $1", document_id
                )
                await conn.executemany(
                    """
                    INSERT INTO compliance_chunk (document_id, ref_article, contenu, embedding)
                    VALUES ($1, $2, $3, $4::vector)
                    """,
                    [
                        (
                            document_id,
                            chunk["ref_article"],
                            chunk["contenu"],
                            ingestion.to_pgvector(vector),
                        )
                        for chunk, vector in zip(document["chunks"], embeddings["vectors"])
                    ],
                )
                await conn.execute(
                    "UPDATE compliance_document SET corpus_hash = $2 WHERE id = $1",
                    document_id,
                    new_hash,
                )
        report["regenerated"] += 1
        report["chunks_added"] += len(document["chunks"])
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
