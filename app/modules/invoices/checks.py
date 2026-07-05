"""Contrôles déterministes d'une facture extraite — aucun LLM (la bonne technique : des règles).

Fonctions pures (dict → list[dict]) : calculées à l'ingestion, stockées en base,
testées unitairement dans tests/test_checks.py.
"""

from decimal import Decimal

# Tolérance d'arrondi sur les rapprochements de totaux (centimes)
ROUNDING_TOLERANCE = Decimal("0.02")

# Taux de TVA français plausibles (%)
PLAUSIBLE_VAT_RATES = (Decimal("0"), Decimal("2.1"), Decimal("5.5"), Decimal("10"), Decimal("20"))

BLOQUANT = "bloquant"
AVERTISSEMENT = "avertissement"

# Mentions dont la checklist conformité vérifie la présence (champ extrait → libellé)
COMPLIANCE_FIELDS = (
    ("supplier_siren", "SIREN du fournisseur"),
    ("invoice_number", "Numéro de facture"),
    ("issue_date", "Date d'émission"),
    ("total_ht", "Montant total HT"),
    ("total_vat", "Montant de la TVA"),
    ("total_ttc", "Montant total TTC"),
    ("due_date", "Date d'échéance"),
)


def _eur(value: Decimal) -> str:
    return f"{value:,.2f}".replace(",", " ").replace(".", ",") + " €"


def _anomaly(code: str, severity: str, message: str) -> dict:
    return {"code": code, "severity": severity, "message": message}


def check_anomalies(header: dict, lines: list[dict]) -> list[dict]:
    """Contrôles de cohérence des valeurs. Chaque anomalie : code, sévérité, message clair."""
    anomalies = []

    total_ht = header.get("total_ht")
    total_vat = header.get("total_vat")
    total_ttc = header.get("total_ttc")

    line_amounts = [line["line_amount_ht"] for line in lines if line.get("line_amount_ht")]
    if line_amounts and total_ht is not None:
        lines_sum = sum(line_amounts)
        if abs(lines_sum - total_ht) > ROUNDING_TOLERANCE:
            anomalies.append(
                _anomaly(
                    "totaux_lignes",
                    BLOQUANT,
                    f"La somme des lignes ({_eur(lines_sum)}) ne correspond pas "
                    f"au total HT ({_eur(total_ht)}).",
                )
            )

    if total_ht is not None and total_vat is not None and total_ttc is not None:
        if abs((total_ht + total_vat) - total_ttc) > ROUNDING_TOLERANCE:
            anomalies.append(
                _anomaly(
                    "totaux_ttc",
                    BLOQUANT,
                    f"HT ({_eur(total_ht)}) + TVA ({_eur(total_vat)}) ne donne pas "
                    f"le TTC ({_eur(total_ttc)}).",
                )
            )

    for label, value in (("HT", total_ht), ("TVA", total_vat), ("TTC", total_ttc)):
        if value is not None and value < 0:
            anomalies.append(
                _anomaly(
                    "montant_negatif",
                    BLOQUANT,
                    f"Le total {label} est négatif ({_eur(value)}) : un avoir doit être "
                    "traité à part.",
                )
            )
    if total_ttc is not None and total_ttc == 0:
        anomalies.append(
            _anomaly("montant_nul", BLOQUANT, "Le total TTC est nul : facture sans objet ?")
        )

    unusual_rates = sorted(
        {
            line["vat_rate"]
            for line in lines
            if line.get("vat_rate") is not None and line["vat_rate"] not in PLAUSIBLE_VAT_RATES
        }
    )
    if unusual_rates:
        rates = ", ".join(f"{rate:g} %".replace(".", ",") for rate in unusual_rates)
        anomalies.append(
            _anomaly(
                "tva_inhabituelle",
                AVERTISSEMENT,
                f"Taux de TVA inhabituel : {rates} (taux français usuels : 0, 2,1, 5,5, 10, 20 %).",
            )
        )

    issue_date = header.get("issue_date")
    due_date = header.get("due_date")
    if issue_date and due_date and due_date < issue_date:
        anomalies.append(
            _anomaly(
                "echeance_incoherente",
                AVERTISSEMENT,
                f"L'échéance ({due_date:%d/%m/%Y}) précède la date d'émission "
                f"({issue_date:%d/%m/%Y}).",
            )
        )

    return anomalies


def check_compliance(header: dict) -> list[dict]:
    """Checklist de PRÉSENCE des mentions attendues d'une facture.

    Purement factuel (le champ est-il renseigné ?) — pas un avis juridique,
    et l'UI l'affiche explicitement.
    """
    return [
        {"field": field, "label": label, "present": header.get(field) is not None}
        for field, label in COMPLIANCE_FIELDS
    ]


def has_blocking(anomalies: list[dict]) -> bool:
    return any(anomaly["severity"] == BLOQUANT for anomaly in anomalies)


def duplicate_anomaly(existing_id: int, existing_number: str | None) -> dict:
    """Anomalie bloquante générée quand un doublon SIREN + numéro est trouvé en base."""
    ref = f"n° {existing_number}" if existing_number else f"id {existing_id}"
    return _anomaly(
        "doublon",
        BLOQUANT,
        f"Doublon probable : une facture {ref} du même fournisseur existe déjà "
        f"(facture #{existing_id}). Ne pas comptabiliser deux fois.",
    )
