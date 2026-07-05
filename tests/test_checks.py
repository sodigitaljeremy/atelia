"""Tests unitaires des contrôles déterministes du module Factures (Slice 2).

Preuve de la logique d'anomalies sans fabriquer de Factur-X invalide :
les fonctions sont pures (dict → list[dict]), pas de DB ni de PDF requis.
"""

from datetime import date
from decimal import Decimal

from app.modules.invoices import checks


def header_ok(**overrides) -> dict:
    base = {
        "supplier_siren": "842563197",
        "invoice_number": "F-2026-001",
        "issue_date": date(2026, 6, 1),
        "due_date": date(2026, 7, 1),
        "total_ht": Decimal("100.00"),
        "total_vat": Decimal("20.00"),
        "total_ttc": Decimal("120.00"),
    }
    base.update(overrides)
    return base


def lines_ok() -> list[dict]:
    return [
        {"line_amount_ht": Decimal("60.00"), "vat_rate": Decimal("20")},
        {"line_amount_ht": Decimal("40.00"), "vat_rate": Decimal("20")},
    ]


def codes(anomalies: list[dict]) -> set[str]:
    return {a["code"] for a in anomalies}


# --- Anomalies --------------------------------------------------------------


def test_facture_saine_aucune_anomalie():
    # `today` injecté : le verdict d'une facture saine ne doit pas dépendre de l'horloge
    assert checks.check_anomalies(header_ok(), lines_ok(), today=date(2026, 6, 15)) == []


def test_somme_lignes_differente_du_total_ht_est_bloquante():
    anomalies = checks.check_anomalies(header_ok(total_ht=Decimal("150.00")), lines_ok())
    (anomalie,) = [a for a in anomalies if a["code"] == "totaux_lignes"]
    assert anomalie["severity"] == checks.BLOQUANT
    assert "100,00 €" in anomalie["message"] and "150,00 €" in anomalie["message"]


def test_tolerance_arrondi_sur_les_totaux():
    # 100,01 vs 100,00 : écart d'un centime, dans la tolérance → pas d'anomalie
    anomalies = checks.check_anomalies(header_ok(total_ht=Decimal("100.01")), lines_ok())
    assert "totaux_lignes" not in codes(anomalies)


def test_ht_plus_tva_different_du_ttc_est_bloquant():
    anomalies = checks.check_anomalies(header_ok(total_ttc=Decimal("130.00")), lines_ok())
    (anomalie,) = [a for a in anomalies if a["code"] == "totaux_ttc"]
    assert anomalie["severity"] == checks.BLOQUANT


def test_taux_tva_improbable_est_un_avertissement():
    lines = [{"line_amount_ht": Decimal("100.00"), "vat_rate": Decimal("13")}]
    anomalies = checks.check_anomalies(
        header_ok(total_vat=Decimal("13"), total_ttc=Decimal("113")), lines
    )
    (anomalie,) = [a for a in anomalies if a["code"] == "tva_inhabituelle"]
    assert anomalie["severity"] == checks.AVERTISSEMENT
    assert "13" in anomalie["message"]


def test_taux_tva_usuels_ne_declenchent_rien():
    for rate in ("0", "2.1", "5.5", "10", "20"):
        lines = [{"line_amount_ht": Decimal("100.00"), "vat_rate": Decimal(rate)}]
        header = header_ok(total_vat=None, total_ttc=None)
        assert "tva_inhabituelle" not in codes(checks.check_anomalies(header, lines))


def test_echeance_avant_emission_est_un_avertissement():
    anomalies = checks.check_anomalies(header_ok(due_date=date(2026, 5, 1)), lines_ok())
    (anomalie,) = [a for a in anomalies if a["code"] == "echeance_incoherente"]
    assert anomalie["severity"] == checks.AVERTISSEMENT


def test_montant_negatif_est_bloquant():
    header = header_ok(
        total_ht=Decimal("-100.00"), total_vat=Decimal("-20.00"), total_ttc=Decimal("-120.00")
    )
    anomalies = checks.check_anomalies(header, [])
    assert "montant_negatif" in codes(anomalies)
    assert checks.has_blocking(anomalies)


def test_ttc_nul_est_bloquant():
    header = header_ok(total_ht=Decimal("0"), total_vat=Decimal("0"), total_ttc=Decimal("0"))
    assert "montant_nul" in codes(checks.check_anomalies(header, []))


def test_champs_absents_ne_plantent_pas():
    header = dict.fromkeys(header_ok())
    assert checks.check_anomalies(header, []) == []


def test_echeance_depassee_est_un_avertissement():
    anomalies = checks.check_anomalies(header_ok(), lines_ok(), today=date(2026, 8, 1))
    (anomalie,) = [a for a in anomalies if a["code"] == "echeance_depassee"]
    assert anomalie["severity"] == checks.AVERTISSEMENT


def test_echeance_future_ou_absente_sans_avertissement():
    # échéance au 01/07, contrôle au 15/06 → rien
    anomalies = checks.check_anomalies(header_ok(), lines_ok(), today=date(2026, 6, 15))
    assert "echeance_depassee" not in codes(anomalies)
    anomalies = checks.check_anomalies(header_ok(due_date=None), lines_ok(), today=date(2026, 8, 1))
    assert "echeance_depassee" not in codes(anomalies)


def test_identifiant_non_siren_signale_fournisseur_etranger():
    anomalies = checks.check_anomalies(header_ok(supplier_siren="ESB28415661"), lines_ok())
    (anomalie,) = [a for a in anomalies if a["code"] == "fournisseur_etranger"]
    assert anomalie["severity"] == checks.AVERTISSEMENT
    assert "ESB28415661" in anomalie["message"]


def test_siren_francais_ou_absent_sans_avertissement_etranger():
    assert "fournisseur_etranger" not in codes(checks.check_anomalies(header_ok(), lines_ok()))
    anomalies = checks.check_anomalies(header_ok(supplier_siren=None), lines_ok())
    assert "fournisseur_etranger" not in codes(anomalies)  # l'absence relève de la conformité


# --- Conformité (présence des mentions) --------------------------------------


def test_compliance_facture_complete():
    result = checks.check_compliance(header_ok())
    assert len(result) == len(checks.COMPLIANCE_FIELDS)
    assert all(item["present"] for item in result)


def test_compliance_signale_les_mentions_absentes():
    result = checks.check_compliance(header_ok(supplier_siren=None, due_date=None))
    absents = {item["field"] for item in result if not item["present"]}
    assert absents == {"supplier_siren", "due_date"}


# --- Doublon / bloquants ------------------------------------------------------


def test_anomalie_doublon_est_bloquante():
    anomalie = checks.duplicate_anomaly(42, "F-2026-001")
    assert anomalie["severity"] == checks.BLOQUANT
    assert "F-2026-001" in anomalie["message"] and "#42" in anomalie["message"]


def test_has_blocking():
    assert not checks.has_blocking([])
    assert not checks.has_blocking([{"severity": checks.AVERTISSEMENT}])
    assert checks.has_blocking([{"severity": checks.AVERTISSEMENT}, {"severity": checks.BLOQUANT}])
