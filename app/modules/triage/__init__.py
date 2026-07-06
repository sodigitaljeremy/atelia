"""Module Triage (M4) — classification zero-shot de messages entrants, garde-fou déterministe.

Sans table : une classification de démonstration est sans état — l'historiser
n'apporterait rien et créerait du bruit (schema_path=None, comme le module suppliers).
"""

from app.core.registry import Module
from app.modules.triage.router import router

MODULE = Module(
    slug="triage",
    titre="Triage des messages entrants",
    probleme="Trier, prioriser et router réclamations et demandes sans dépouillement manuel.",
    technique="Classification LLM zero-shot + garde-fou déterministe",
    icone="📨",
    router=router,
    nav=[("Triage", "/triage", "triage")],
)
