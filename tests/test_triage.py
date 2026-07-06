"""Tests du module Triage — LLM mocké ; le garde-fou est testé SEUL, sans aucun LLM."""

import asyncio
import json

from app.core import llm
from app.modules.triage import classifier

JSON_OK = json.dumps(
    {
        "categorie": "Qualité",
        "priorite": "moyenne",
        "resume": "Réclamation sur la texture d'un lot de sauce.",
        "service_destinataire": "Service Qualité",
        "entites": {"produit": "sauce basquaise", "num_lot": "L2412"},
    },
    ensure_ascii=False,
)


def _fake_llm(replies):
    replies = list(replies)
    calls = []

    async def fake(messages, tools=None, max_tokens=1024):
        calls.append(list(messages))
        return {"content": replies.pop(0), "tool_calls": [], "message": {}}

    fake.calls = calls
    return fake


# --- Garde-fou déterministe : DOIT marcher sans LLM -------------------------------


def test_garde_fou_detecte_les_signaux_sans_llm():
    cas = {
        "il y a des traces de noisette non mentionnées sur l'étiquette": True,
        "j'ai trouvé un morceau de verre dans le bocal": True,
        "ma fille allergique a fait une réaction après la piperade": True,
        "le couvercle du bocal est bombé et l'odeur suspecte": True,
        "mon fils a été malade après avoir mangé vos rillettes": True,
        "demande de rappel de lot suite à suspicion de listeria": True,
        # messages sains : aucun déclenchement
        "la facture F-118 est en double avec une TVA erronée": False,
        "livraison C-88412 non reçue, restaurant à court de stock": False,
        "nous souhaitons référencer vos conserves, envoyez vos tarifs": False,
    }
    for message, attendu in cas.items():
        signaux = classifier.security_guard(message)
        assert bool(signaux) is attendu, f"{message!r} → {signaux}"


def test_garde_fou_force_le_jugement_du_llm(monkeypatch):
    """LE test : le LLM juge « Qualité / moyenne », le garde-fou force « Sécurité / critique »."""
    monkeypatch.setattr(llm, "complete_messages", _fake_llm([JSON_OK]))
    result = asyncio.run(
        classifier.classify("Petite remarque : un éclat de verre dans le bocal, rien de grave.")
    )
    c = result["classification"]
    assert result["garde_fou"] is True and result["signaux"]
    assert c.priorite == "critique"  # forcée, le LLM avait dit « moyenne »
    assert c.categorie == "Sécurité"  # forcée, le LLM avait dit « Qualité »
    assert c.service_destinataire == classifier.SECURITY_SERVICE
    assert c.entites["num_lot"] == "L2412"  # le reste du travail du LLM est conservé


def test_message_sain_pas_de_forcage(monkeypatch):
    monkeypatch.setattr(llm, "complete_messages", _fake_llm([JSON_OK]))
    result = asyncio.run(classifier.classify("La sauce du lot L2412 est fade."))
    assert result["garde_fou"] is False
    assert result["classification"].priorite == "moyenne"  # le jugement du LLM est respecté


# --- Cadre contraint : parse, validation, retry ------------------------------------


def test_json_invalide_un_retry_puis_erreur_propre(monkeypatch):
    fake = _fake_llm(["Voici ma réponse en prose, sans JSON.", "toujours pas de JSON"])
    monkeypatch.setattr(llm, "complete_messages", fake)
    result = asyncio.run(classifier.classify("message quelconque"))
    assert result["classification"] is None
    assert "réessayez" in result["error"]
    assert len(fake.calls) == 2  # exactement un retry, pas plus
    # le retry contient le motif de l'échec
    assert "invalide" in fake.calls[1][-1]["content"]


def test_json_invalide_puis_retry_reussi(monkeypatch):
    fake = _fake_llm(["du texte sans structure", JSON_OK])
    monkeypatch.setattr(llm, "complete_messages", fake)
    result = asyncio.run(classifier.classify("message quelconque"))
    assert result["error"] is None
    assert result["classification"].categorie == "Qualité"


def test_categorie_hors_liste_rejetee_par_pydantic(monkeypatch):
    hors_liste = JSON_OK.replace("Qualité", "Réclamations")  # catégorie inventée
    fake = _fake_llm([hors_liste, hors_liste])
    monkeypatch.setattr(llm, "complete_messages", fake)
    result = asyncio.run(classifier.classify("message"))
    assert result["classification"] is None and result["error"] is not None
    assert "categorie" in fake.calls[1][-1]["content"]  # le motif cite le champ fautif


def test_erreur_llm_message_propre_et_signaux_conserves(monkeypatch):
    async def failing(messages, tools=None, max_tokens=1024):
        raise RuntimeError("Rate limit")

    monkeypatch.setattr(llm, "complete_messages", failing)
    result = asyncio.run(classifier.classify("morceau de verre dans le bocal"))
    assert "réessayez" in result["error"]
    # même sans LLM, les signaux de sécurité remontent (le garde-fou n'en dépend pas)
    assert result["garde_fou"] is True and result["signaux"]


def test_parse_tolere_les_fences_et_entites_numeriques():
    contenu = f"```json\n{JSON_OK.replace('"L2412"', '2412')}\n```"
    classification, motif = classifier._parse(contenu)
    assert motif == ""
    assert classification.entites["num_lot"] == "2412"  # coercition en str
