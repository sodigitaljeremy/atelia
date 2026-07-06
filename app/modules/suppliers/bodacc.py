"""Client de l'API BODACC (bodacc-datadila.opendatasoft.com — DILA, annonces légales).

Dataset « annonces-commerciales », filtré sur familleavis="collective" (BODACC A,
procédures collectives : sauvegarde, redressement, liquidation). Data publique de
l'État, sans clé (ADR-104). Endpoint et filtre vérifiés par appel réel le 06/07/2026.

Rappel métier crucial : l'ABSENCE d'annonce ne prouve PAS la bonne santé de
l'entreprise (absence non probante) — la nuance est imposée à l'agent dans son prompt.
"""

import json

import httpx

from app.core.config import settings
from app.modules.suppliers.client import SearchError

TIMEOUT_S = 5.0


def parse_procedures(payload: dict) -> list[dict]:
    """Normalise les annonces BODACC en événements affichables — fonction pure."""
    procedures = []
    for record in payload.get("results", []):
        jugement = record.get("jugement")
        if isinstance(jugement, str):
            try:
                jugement = json.loads(jugement)
            except ValueError:
                jugement = {}
        jugement = jugement or {}
        procedures.append(
            {
                "nature": jugement.get("nature")
                or record.get("familleavis_lib")
                or "Procédure collective",
                "date_jugement": jugement.get("date") or "—",
                "date_parution": record.get("dateparution") or "—",
                "tribunal": record.get("tribunal") or "—",
            }
        )
    return procedures


async def search_procedures(
    siren: str, limit: int = 5, transport: httpx.AsyncBaseTransport | None = None
) -> list[dict]:
    """Annonces de procédures collectives pour un SIREN (plus récentes d'abord).

    Lève SearchError (messages affichables), jamais de crash. Le SIREN est validé
    strictement (9 chiffres) — il est interpolé dans la clause where ODSQL.
    """
    siren = "".join(ch for ch in siren if ch.isdigit())
    if len(siren) != 9:
        raise SearchError("SIREN invalide pour le BODACC (9 chiffres attendus).")
    params = {
        "where": f'registre="{siren}" AND familleavis="collective"',
        "order_by": "dateparution DESC",
        "limit": limit,
    }
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT_S, transport=transport) as client:
            response = await client.get(settings.bodacc_api_url, params=params)
    except httpx.TimeoutException as exc:
        raise SearchError("Le BODACC n'a pas répondu à temps (5 s) — réessayez.") from exc
    except httpx.HTTPError as exc:
        raise SearchError("Le BODACC est injoignable pour le moment.") from exc

    if response.status_code == 429:
        raise SearchError("Limite de débit du BODACC atteinte — patientez quelques secondes.")
    if response.status_code >= 400:
        raise SearchError(
            f"Le BODACC a refusé la requête (code {response.status_code}) — réessayez."
        )
    try:
        payload = response.json()
    except ValueError as exc:
        raise SearchError("Réponse illisible du BODACC — réessayez.") from exc
    return parse_procedures(payload)
