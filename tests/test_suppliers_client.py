"""Tests du client API Recherche d'entreprises — AUCUN appel réseau.

parse_results est pure ; les chemins d'erreur de search_companies sont exercés via
httpx.MockTransport injecté (asyncio.run suffit, pas besoin de pytest-asyncio).
"""

import asyncio

import httpx
import pytest

from app.modules.suppliers import client

# Extrait figé (structure réelle de l'API, vérifiée en live le 06/07/2026)
PAYLOAD = {
    "results": [
        {
            "siren": "552081317",
            "nom_complet": "ELECTRICITE DE FRANCE (EDF)",
            "etat_administratif": "A",
            "activite_principale": "35.11Z",
            "tranche_effectif_salarie": "53",
            "date_creation": "1955-01-01",
            "siege": {"adresse": "22 AVENUE DE WAGRAM 75008 PARIS"},
            "dirigeants": [
                {"nom": "Fontana", "prenoms": "Bernard", "qualite": "Président directeur général"},
                {"denomination": "KPMG SA", "qualite": "Commissaire aux comptes"},
            ],
        },
        {
            "siren": "344260286",
            "nom_complet": "VIRGIN STORES",
            "etat_administratif": "C",
            "activite_principale": "47.63Z",
            "tranche_effectif_salarie": None,
            "date_creation": None,
            "siege": {"code_postal": "75009", "libelle_commune": "PARIS"},
            "dirigeants": [],
        },
    ]
}


def _search_with(handler):
    return asyncio.run(client.search_companies("test", transport=httpx.MockTransport(handler)))


# --- parse_results (pure) -----------------------------------------------------


def test_parse_normalise_une_fiche_complete():
    fiche = client.parse_results(PAYLOAD)[0]
    assert fiche["nom"] == "ELECTRICITE DE FRANCE (EDF)"
    assert fiche["etat"] == "Active" and fiche["active"] is True
    assert fiche["effectif"] == "10 000 salariés et plus"
    assert fiche["siege"] == "22 AVENUE DE WAGRAM 75008 PARIS"
    assert fiche["dirigeants"] == [
        "Bernard Fontana — Président directeur général",
        "KPMG SA — Commissaire aux comptes",
    ]


def test_parse_entreprise_cessee_et_champs_absents():
    fiche = client.parse_results(PAYLOAD)[1]
    assert fiche["etat"] == "Cessée" and fiche["active"] is False
    assert fiche["effectif"] == "non renseigné"
    assert fiche["creation"] == "—"
    assert fiche["siege"] == "75009, PARIS"  # repli code postal + commune


def test_parse_reponse_vide():
    assert client.parse_results({"results": []}) == []
    assert client.parse_results({}) == []


# --- search_companies : chemins d'erreur (MockTransport, zéro réseau) ----------


def test_recherche_nominale_via_transport_mocke():
    fiches = _search_with(lambda request: httpx.Response(200, json=PAYLOAD))
    assert len(fiches) == 2 and fiches[0]["siren"] == "552081317"


def test_api_en_erreur_serveur():
    with pytest.raises(client.SearchError, match="indisponible"):
        _search_with(lambda request: httpx.Response(500))


def test_limite_de_debit():
    with pytest.raises(client.SearchError, match="débit"):
        _search_with(lambda request: httpx.Response(429))


def test_requete_refusee_4xx():
    with pytest.raises(client.SearchError, match="code 400"):
        _search_with(lambda request: httpx.Response(400))


def test_api_injoignable():
    def handler(request):
        raise httpx.ConnectError("réseau coupé")

    with pytest.raises(client.SearchError, match="injoignable"):
        _search_with(handler)


def test_timeout():
    def handler(request):
        raise httpx.ReadTimeout("trop lent")

    with pytest.raises(client.SearchError, match="pas répondu à temps"):
        _search_with(handler)


def test_json_illisible():
    with pytest.raises(client.SearchError, match="illisible"):
        _search_with(lambda request: httpx.Response(200, text="<html>pas du json</html>"))
