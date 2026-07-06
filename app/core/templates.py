"""Env Jinja partagé : layout commun, filtres de formatage, contexte global (branding, nav).

Chaque module instancie ses templates via module_templates() — son dossier propre
s'ajoute au dossier partagé (base.html), sans import circulaire avec le registre.
"""

from pathlib import Path

from fastapi.templating import Jinja2Templates

from app.core.config import settings

SHARED_DIR = Path(__file__).parent.parent / "shared" / "templates"


def _fmt_eur(value) -> str:
    if value is None:
        return "—"
    return f"{value:,.2f}".replace(",", " ").replace(".", ",") + " €"


def _fmt_qty(value) -> str:
    if value is None:
        return "—"
    text = f"{value:.3f}".rstrip("0").rstrip(".")
    return text.replace(".", ",")


def _excerpt(value, length: int = 400) -> str:
    """Tronque au dernier mot entier avant `length` — jamais de coupe en plein mot."""
    text = value or ""
    if len(text) <= length:
        return text
    cut = text[:length].rsplit(" ", 1)[0].rstrip(",;:.")
    return f"{cut}…"


def _global_context(request) -> dict:
    # Import local : le registre importe les modules, qui importent ce fichier.
    from app.core import registry

    return {"company_name": settings.company_name, "nav_modules": registry.modules}


def module_templates(module_dir: Path | None = None) -> Jinja2Templates:
    directories = [SHARED_DIR] + ([module_dir] if module_dir else [])
    templates = Jinja2Templates(directory=directories, context_processors=[_global_context])
    templates.env.filters["eur"] = _fmt_eur
    templates.env.filters["qty"] = _fmt_qty
    templates.env.filters["extrait"] = _excerpt
    return templates
