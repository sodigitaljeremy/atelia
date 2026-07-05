"""Génère des factures Factur-X VOLONTAIREMENT incohérentes dans samples/ (préfixe anomalie_).

Le XML CII est présent et XSD-valide (seules les VALEURS sont incohérentes — pas de
validation schematron à la génération) : l'extraction déterministe réussit, et ce sont
les contrôles de checks.py qui doivent attraper l'incohérence. Objectif : démo des
anomalies. Lancement : uv run scripts/generate_broken_samples.py
"""

import sys
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

from facturx import generate_from_binary

sys.path.insert(0, str(Path(__file__).parent))
from generate_samples import SAMPLES_DIR, build_cii_xml, build_pdf, compute_totals, money  # noqa: E402

# Chaque cas : fournisseur fictif distinct (SIREN + numéro uniques → pas de contrôle
# doublon parasite), une seule incohérence injectée pour isoler le contrôle visé.
BROKEN_CASES = [
    {
        # HT + TVA ≠ TTC (TTC gonflé de 100 €) → anomalie BLOQUANTE « totaux_ttc »
        "case": "totaux-ttc",
        "tamper": lambda totals: totals.update(ttc=totals["ttc"] + Decimal("100")),
        "supplier": {
            "slug": "minoterie-garonne",
            "name": "Minoterie de la Garonne SA",
            "siren": "612845379",
            "vat": "FR23612845379",
            "address": ("2 quai des Moulins", "47000", "Agen"),
            "number": "MG-2026-0733",
            "issue": date(2026, 6, 30),
            "lines": [
                (
                    "Farine de blé T55, sac 25 kg",
                    Decimal("40"),
                    "KGM",
                    Decimal("18.90"),
                    Decimal("5.5"),
                ),
            ],
        },
    },
    {
        # Somme des lignes ≠ total HT (HT gonflé de 50 €, TTC recalculé pour isoler
        # le seul contrôle « totaux_lignes ») → anomalie BLOQUANTE
        "case": "somme-lignes",
        "tamper": lambda totals: totals.update(
            ht=totals["ht"] + Decimal("50"), ttc=totals["ht"] + Decimal("50") + totals["vat"]
        ),
        "supplier": {
            "slug": "cartonnages-albret",
            "name": "Cartonnages d'Albret SARL",
            "siren": "753916428",
            "vat": "FR59753916428",
            "address": ("14 rue des Fabriques", "40800", "Aire-sur-l'Adour"),
            "number": "CA-2026-0512",
            "issue": date(2026, 6, 27),
            "lines": [
                (
                    "Barquette carton kraft 750 ml (x250)",
                    Decimal("10"),
                    "H87",
                    Decimal("21.30"),
                    Decimal("20"),
                ),
                (
                    "Film étirable alimentaire 300 m",
                    Decimal("18"),
                    "H87",
                    Decimal("6.40"),
                    Decimal("20"),
                ),
            ],
        },
    },
    {
        # Échéance 15 jours AVANT l'émission → anomalie de cohérence « echeance_incoherente »
        "case": "echeance",
        "due_offset_days": -15,
        "supplier": {
            "slug": "transports-bigourdans",
            "name": "Transports Bigourdans Express",
            "siren": "894207156",
            "vat": "FR07894207156",
            "address": ("Zone fret 4, rue des Convoyeurs", "65420", "Ibos"),
            "number": "TB-2026-1187",
            "issue": date(2026, 7, 1),
            "lines": [
                (
                    "Navette palette 65 → 31, tournée hebdo",
                    Decimal("4"),
                    "H87",
                    Decimal("87.00"),
                    Decimal("20"),
                ),
            ],
        },
    },
]


def main() -> None:
    SAMPLES_DIR.mkdir(exist_ok=True)
    for case in BROKEN_CASES:
        supplier = case["supplier"]
        totals = compute_totals(supplier["lines"])
        if "tamper" in case:
            case["tamper"](totals)
        due = supplier["issue"] + timedelta(days=case.get("due_offset_days", 30))
        xml_bytes = build_cii_xml(supplier, totals, due)
        pdf_bytes = build_pdf(supplier, totals, due)
        facturx_pdf = generate_from_binary(pdf_bytes, xml_bytes)
        target = SAMPLES_DIR / f"anomalie_{case['case']}_{supplier['number']}.pdf"
        target.write_bytes(facturx_pdf)
        print(f"OK  {target.name}  HT {money(totals['ht'])} €  TTC {money(totals['ttc'])} €")


if __name__ == "__main__":
    main()
