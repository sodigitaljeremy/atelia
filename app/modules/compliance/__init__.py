"""Module Conformité (M2) — RAG sur corpus réglementaire officiel. Phase 1 : indexation + recherche."""

from pathlib import Path

from app.core.registry import Module
from app.modules.compliance import repository
from app.modules.compliance.router import router

MODULE = Module(
    slug="compliance",
    titre="Assistant conformité",
    probleme="Retrouver la règle exacte (étiquetage, allergènes) sans éplucher les textes officiels.",
    technique="RAG sourcé sur pgvector — réponses citées, « je ne sais pas » hors corpus",
    icone="📚",
    router=router,
    schema_path=Path(__file__).parent / "schema.sql",
    nav=[("Conformité", "/compliance", "compliance")],
    ordre=2,
    on_startup=repository.ingest_corpus_best_effort,
)
