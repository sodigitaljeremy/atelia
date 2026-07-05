"""Registre des modules enfichables (ADR-101).

Un module = un package dans app/modules/ exposant un objet MODULE (instance de
Module ci-dessous). Le registre les découvre à l'import : déposer un nouveau
package suffit à le brancher (router monté, schéma appliqué, tuile sur le hub).
"""

import importlib
import pkgutil
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
    schema_path: Path  # schema.sql idempotent, appliqué au démarrage par core.db
    nav: list[tuple[str, str, str]] = field(default_factory=list)  # (libellé, url, clé active)


def _discover() -> list[Module]:
    """Importe chaque package de app/modules/ et collecte son objet MODULE."""
    import app.modules

    found = []
    for info in pkgutil.iter_modules(app.modules.__path__):
        if not info.ispkg:
            continue
        package = importlib.import_module(f"app.modules.{info.name}")
        found.append(package.MODULE)
    return sorted(found, key=lambda module: module.slug)


modules: list[Module] = _discover()
