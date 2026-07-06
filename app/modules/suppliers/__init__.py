"""Module Fournisseurs (M3-a) — vérification d'entreprises via l'API publique de l'État."""

from app.core.registry import Module
from app.modules.suppliers.router import router

MODULE = Module(
    slug="suppliers",
    titre="Fiabilité fournisseurs",
    probleme="Vérifier en direct qu'une entreprise existe légalement et est active, sans ressaisie.",
    technique="Agent function-calling sur API publiques (RNE/Sirene, BODACC)",
    icone="🔎",
    router=router,
    nav=[("Fournisseurs", "/suppliers", "suppliers")],
    ordre=3,
)
