"""Module Factures fournisseurs (M1) — extraction déterministe Factur-X + validation humaine."""

from pathlib import Path

from app.core.registry import Module
from app.modules.invoices import repository
from app.modules.invoices.router import router

MODULE = Module(
    slug="invoices",
    titre="Factures fournisseurs",
    probleme="Éliminer la saisie manuelle des factures (~26 € et 5 min par facture papier).",
    technique="Extraction déterministe Factur-X + human-in-the-loop",
    icone="🧾",
    router=router,
    schema_path=Path(__file__).parent / "schema.sql",
    nav=[("Factures", "/invoices", "invoices"), ("Gains", "/dashboard", "dashboard")],
    on_startup=repository.backfill_gain_events,
)
