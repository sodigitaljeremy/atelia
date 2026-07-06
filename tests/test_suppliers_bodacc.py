"""Tests du client BODACC — AUCUN appel réseau (payload figé + MockTransport)."""

import asyncio
import json

import httpx
import pytest

from app.modules.suppliers import bodacc
from app.modules.suppliers.client import SearchError

# Structure réelle de l'API OpenDataSoft (vérifiée en live le 06/07/2026) :
# le champ jugement arrive comme une chaîne JSON imbriquée.
PAYLOAD = {
    "total_count": 2,
    "results": [
        {
            "dateparution": "2021-04-25",
            "familleavis_lib": "Procédures collectives",
            "commercant": "CAMAIEU INTERNATIONAL",
            "tribunal": "TRIBUNAL DE COMMERCE DE LILLE MÉTROPOLE",
            "jugement": json.dumps(
                {"nature": "Jugement de conversion en liquidation judiciaire", "date": "2021-04-14"}
            ),
        },
        {
            "dateparution": "2020-08-30",
            "familleavis_lib": "Procédures collectives",
            "commercant": "CAMAIEU INTERNATIONAL",
            "tribunal": "Greffe du Tribunal de Commerce de Lille Métropole",
            "jugement": None,
        },
    ],
}


def _search_with(handler, siren="345086177"):
    return asyncio.run(bodacc.search_procedures(siren, transport=httpx.MockTransport(handler)))


def test_parse_normalise_les_annonces():
    procedures = bodacc.parse_procedures(PAYLOAD)
    assert procedures[0]["nature"] == "Jugement de conversion en liquidation judiciaire"
    assert procedures[0]["date_jugement"] == "2021-04-14"
    assert procedures[0]["tribunal"] == "TRIBUNAL DE COMMERCE DE LILLE MÉTROPOLE"
    # jugement absent → repli sur le libellé de famille
    assert procedures[1]["nature"] == "Procédures collectives"
    assert procedures[1]["date_jugement"] == "—"


def test_parse_reponse_vide():
    assert bodacc.parse_procedures({"total_count": 0, "results": []}) == []
    assert bodacc.parse_procedures({}) == []


def test_recherche_nominale_et_clause_where(monkeypatch):
    seen = {}

    def handler(request):
        seen["where"] = request.url.params["where"]
        return httpx.Response(200, json=PAYLOAD)

    procedures = _search_with(handler)
    assert len(procedures) == 2
    assert seen["where"] == 'registre="345086177" AND familleavis="collective"'


def test_siren_invalide_refuse_avant_reseau():
    # validation stricte : le SIREN est interpolé dans la clause where (anti-injection ODSQL)
    with pytest.raises(SearchError, match="SIREN invalide"):
        asyncio.run(bodacc.search_procedures('x" OR 1=1'))


def test_erreur_serveur():
    with pytest.raises(SearchError, match="refusé|indisponible|réessayez"):
        _search_with(lambda request: httpx.Response(500))


def test_injoignable_et_timeout():
    def down(request):
        raise httpx.ConnectError("réseau coupé")

    with pytest.raises(SearchError, match="injoignable"):
        _search_with(down)

    def slow(request):
        raise httpx.ReadTimeout("trop lent")

    with pytest.raises(SearchError, match="pas répondu à temps"):
        _search_with(slow)


def test_json_illisible():
    with pytest.raises(SearchError, match="illisible"):
        _search_with(lambda request: httpx.Response(200, text="<html>"))
