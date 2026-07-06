"""Routes du module Triage : page d'essai + fragment de classification (HTMX)."""

from pathlib import Path

from fastapi import APIRouter, Form, Request

from app.core.templates import module_templates
from app.modules.triage import classifier

templates = module_templates(Path(__file__).parent / "templates")

router = APIRouter(include_in_schema=False)

# Exemples SYNTHÉTIQUES (aucune vraie réclamation — confidentialité), mix métier
# conserverie. Le dernier est le piège volontaire : ton anodin, signal de sécurité
# réel → il démontre le forçage du garde-fou par-dessus le jugement du LLM.
EXAMPLES = [
    (
        "Réclamation qualité",
        "Bonjour, la sauce basquaise du lot L2412 achetée la semaine dernière est très "
        "liquide et fade par rapport à d'habitude. Trois clients de mon épicerie s'en "
        "sont plaints. Pouvez-vous vérifier ce lot ?",
    ),
    (
        "Problème de livraison",
        "Commande C-88412 prévue lundi toujours pas reçue. Mon restaurant est à court de "
        "piperade pour le week-end, c'est urgent, merci de me rappeler aujourd'hui.",
    ),
    (
        "Demande de référencement",
        "Bonjour, nous sommes une épicerie fine à Bordeaux et souhaiterions référencer vos "
        "conserves de la gamme terroir. Pouvez-vous nous envoyer votre catalogue et vos "
        "tarifs professionnels ?",
    ),
    (
        "Erreur de facturation",
        "La facture F-2026-118 nous est parvenue en double et le taux de TVA appliqué sur "
        "les bocaux 720 ml semble erroné (20 % au lieu de 5,5 %). Merci de nous adresser "
        "un avoir.",
    ),
    (
        "Remarque « anodine » (piège)",
        "Petite remarque en passant : il me semble qu'il y a des traces de noisette non "
        "mentionnées sur l'étiquette de votre caviar d'aubergine. Rien de grave, je voulais "
        "juste vous le signaler, sinon très bon produit !",
    ),
]


@router.get("/triage")
async def triage_home(request: Request):
    return templates.TemplateResponse(
        request, "triage.html", {"examples": EXAMPLES, "active": "triage"}
    )


@router.post("/triage/classify")
async def triage_classify(request: Request, message: str = Form("")):
    """Fragment HTMX : classification structurée + état du garde-fou sécurité."""
    message = message.strip()
    if not message:
        return templates.TemplateResponse(
            request,
            "_classification.html",
            {"error": "Collez un message à classer.", "result": None},
        )
    result = await classifier.classify(message)
    return templates.TemplateResponse(
        request,
        "_classification.html",
        {
            "result": result["classification"],
            "garde_fou": result["garde_fou"],
            "signaux": result["signaux"],
            "error": result["error"],
        },
    )
