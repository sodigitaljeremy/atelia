"""Routes du module Fournisseurs : page de recherche + fragment de résultats (HTMX)."""

from pathlib import Path

from fastapi import APIRouter, Form, Request

from app.core.templates import module_templates
from app.modules.suppliers.client import SearchError, search_companies

templates = module_templates(Path(__file__).parent / "templates")

router = APIRouter(include_in_schema=False)

# Exemples réels et publics, vérifiés via l'API — cas variés : active/grande, service
# public, commerce international, et une entreprise cessée (données ouvertes de l'État,
# hors fiction « Conserverie du Val » — ADR-102 respecté par séparation explicite).
EXAMPLES = [
    ("EDF", "552081317", "énergie — grande entreprise active"),
    ("La Poste", "356000000", "service public"),
    ("Decathlon", "306138900", "commerce international"),
    ("Virgin Stores", "344260286", "cessée (liquidation 2013)"),
]


@router.get("/suppliers")
async def suppliers_home(request: Request):
    return templates.TemplateResponse(
        request, "suppliers.html", {"examples": EXAMPLES, "active": "suppliers"}
    )


@router.post("/suppliers/search")
async def suppliers_search(request: Request, q: str = Form("")):
    """Fragment HTMX : résultats ou message d'erreur propre — jamais de crash."""
    q = q.strip()
    context = {"query": q, "companies": [], "error": None, "searched": True}
    if not q:
        context["error"] = "Saisissez un nom d'entreprise ou un SIREN (9 chiffres)."
    else:
        try:
            context["companies"] = await search_companies(q)
        except SearchError as exc:
            context["error"] = str(exc)
    return templates.TemplateResponse(request, "_results.html", context)
