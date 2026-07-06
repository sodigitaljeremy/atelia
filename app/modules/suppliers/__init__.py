"""Module Fournisseurs (M3-a) — vérification d'entreprises via l'API publique de l'État."""

from app.core.registry import Module
from app.modules.suppliers.router import router

MODULE = Module(
    slug="suppliers",
    titre="Fiabilité fournisseurs",
    probleme="Vérifier en direct qu'une entreprise existe légalement et est active, sans ressaisie.",
    technique="API publiques de l'État en direct (RNE + Sirene)",
    icone="🔎",
    router=router,
    nav=[("Fournisseurs", "/suppliers", "suppliers")],
)
