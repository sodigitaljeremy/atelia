"""Registre des modules enfichables (ADR-101).

Un module = un package dans app/modules/ exposant un objet MODULE (instance de
Module ci-dessous). Le registre les découvre à l'import : déposer un nouveau
package suffit à le brancher (router monté, schéma appliqué, tuile sur le hub).
"""

import importlib
import pkgutil
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from pathlib import Path

from fastapi import APIRouter


@dataclass(frozen=True)
class Module:
    """Contrat d'un module : routes + tables + métadonnées de navigation."""

    slug: str
    titre: str
    probleme: str  # le problème métier résolu, en une phrase
    technique: str  # la technique IA/data démontrée (badge sur le hub)
    icone: str
    router: APIRouter
    # schema.sql idempotent, appliqué au démarrage par core.db — None si le module n'a pas de table
    schema_path: Path | None = None
    nav: list[tuple[str, str, str]] = field(default_factory=list)  # (libellé, url, clé active)
    # Hook optionnel exécuté au démarrage après l'application des schémas
    # (migrations de données idempotentes, backfills…)
    on_startup: Callable[[], Awaitable[None]] | None = None
    # Position dans le hub et la nav (ordre narratif : déterministe → RAG → agent → NLP)
    ordre: int = 99


def _discover() -> list[Module]:
    """Importe chaque package de app/modules/ et collecte son objet MODULE."""
    import app.modules

    found = []
    for info in pkgutil.iter_modules(app.modules.__path__):
        if not info.ispkg:
            continue
        package = importlib.import_module(f"app.modules.{info.name}")
        found.append(package.MODULE)
    return sorted(found, key=lambda module: (module.ordre, module.slug))


_modules: list[Module] | None = None


def __getattr__(name: str):
    # Découverte paresseuse (PEP 562) : `registry.modules` ne déclenche l'import des
    # modules qu'au premier accès — jamais pendant l'import d'un module lui-même
    # (sinon import circulaire, ex. tests important directement un sous-module).
    if name == "modules":
        global _modules
        if _modules is None:
            _modules = _discover()
        return _modules
    raise AttributeError(name)
