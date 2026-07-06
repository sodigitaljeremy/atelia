"""Routes du module Conformité — phase 1 : état du corpus + recherche sémantique de test."""

from pathlib import Path

from fastapi import APIRouter, Form, Request

from app.core.templates import module_templates
from app.modules.compliance import rag, repository

templates = module_templates(Path(__file__).parent / "templates")

router = APIRouter(include_in_schema=False)


@router.get("/compliance")
async def compliance_home(request: Request):
    documents = await repository.corpus_status()
    return templates.TemplateResponse(
        request,
        "compliance.html",
        {"documents": documents, "active": "compliance"},
    )


@router.post("/compliance/ask")
async def compliance_ask(request: Request, q: str = Form("")):
    """Fragment HTMX : réponse RAG citée — grounding strict, sources issues du retrieval."""
    q = q.strip()
    if not q:
        return templates.TemplateResponse(
            request, "_answer.html", {"error": "Posez une question.", "result": None, "query": q}
        )
    result = await rag.answer(q)
    return templates.TemplateResponse(
        request,
        "_answer.html",
        {"query": q, "result": result, "error": result["error"]},
    )


@router.post("/compliance/search")
async def compliance_search(request: Request, q: str = Form("")):
    """Fragment HTMX : passages les plus proches (réf + score) — AUCUN LLM rédacteur ici."""
    q = q.strip()
    context = {"query": q, "chunks": [], "error": None}
    if not q:
        context["error"] = "Saisissez une question ou des mots-clés."
    else:
        try:
            context["chunks"] = await repository.search_chunks(q)
        except Exception:
            context["error"] = (
                "La vectorisation de la requête a échoué (service d'embedding indisponible) — "
                "réessayez dans quelques secondes."
            )
    return templates.TemplateResponse(request, "_chunks.html", context)
