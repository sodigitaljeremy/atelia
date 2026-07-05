"""Génère des factures Factur-X synthétiques (profil EN 16931) dans samples/.

Fournisseurs food factices mais réalistes (verre, épices, emballages) — aucune
donnée réelle (ADR-004). Lancement : uv run scripts/generate_samples.py
"""

import sys
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from io import BytesIO
from pathlib import Path
from xml.sax.saxutils import escape

from facturx import generate_from_binary
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas

sys.path.insert(0, str(Path(__file__).parent.parent))
from app.core.config import settings  # noqa: E402 — la PME fictive vient de la config (ADR-102)

SAMPLES_DIR = Path(__file__).parent.parent / "samples"

BUYER = {
    "name": settings.company_name,
    "address": ("Zone artisanale des Trois Vallées", "65000", "Val-d'Adour"),
}

# (désignation, quantité, code unité UN/ECE, prix unitaire HT, taux TVA %)
SUPPLIERS = [
    {
        "slug": "verrerie-sud-ouest",
        "name": "Verrerie du Sud-Ouest SAS",
        "siren": "842563197",
        "vat": "FR32842563197",
        "address": ("12 route des Fours", "40100", "Dax"),
        "number": "VSO-2026-0187",
        "issue": date(2026, 6, 12),
        "lines": [
            (
                "Bocal verre 720 ml Twist-Off 82",
                Decimal("2400"),
                "H87",
                Decimal("0.42"),
                Decimal("20"),
            ),
            (
                "Couvercle TO 82 pasteurisable, vernis alimentaire",
                Decimal("2400"),
                "H87",
                Decimal("0.11"),
                Decimal("20"),
            ),
            ("Palette Europe consignée", Decimal("4"), "H87", Decimal("18.50"), Decimal("20")),
        ],
    },
    {
        "slug": "epices-occitanes",
        "name": "Épices Occitanes SARL",
        "siren": "512407386",
        "vat": "FR47512407386",
        "address": ("4 chemin des Séchoirs", "31300", "Toulouse"),
        "number": "EO-2026-0912",
        "issue": date(2026, 6, 18),
        "lines": [
            (
                "Piment d'Espelette AOP moulu, seau 1 kg",
                Decimal("6"),
                "KGM",
                Decimal("64.90"),
                Decimal("5.5"),
            ),
            (
                "Poivre noir de Sarawak grains, sac 5 kg",
                Decimal("10"),
                "KGM",
                Decimal("21.40"),
                Decimal("5.5"),
            ),
            (
                "Thym de garrigue séché, carton 2 kg",
                Decimal("8"),
                "KGM",
                Decimal("18.75"),
                Decimal("5.5"),
            ),
        ],
    },
    {
        "slug": "emballages-bigorre",
        "name": "Emballages Bigorre & Fils",
        "siren": "391824655",
        "vat": "FR68391824655",
        "address": ("18 avenue des Palombières", "65000", "Tarbes"),
        "number": "EB-2026-1204",
        "issue": date(2026, 6, 25),
        "lines": [
            (
                "Caisse carton double cannelure 40x30x24",
                Decimal("500"),
                "H87",
                Decimal("0.86"),
                Decimal("20"),
            ),
            (
                "Étiquette adhésive bobine 80x120 (x1000)",
                Decimal("12"),
                "H87",
                Decimal("34.00"),
                Decimal("20"),
            ),
        ],
    },
    {
        # Taux de TVA volontairement inhabituel (13 %) : XSD-valide, mais déclenche
        # l'avertissement « tva_inhabituelle » des contrôles — pour la démo Slice 2.
        "slug": "maraichers-adour",
        "name": "Les Maraîchers de l'Adour SCA",
        "siren": "428713946",
        "vat": "FR21428713946",
        "address": ("7 chemin des Saligues", "64100", "Bayonne"),
        "number": "MA-2026-0455",
        "issue": date(2026, 6, 28),
        "lines": [
            (
                "Piquillos frais calibre 40+, caisse 10 kg",
                Decimal("30"),
                "KGM",
                Decimal("3.85"),
                Decimal("13"),
            ),
            (
                "Oignons doux des Landes, sac 25 kg",
                Decimal("8"),
                "KGM",
                Decimal("1.90"),
                Decimal("13"),
            ),
        ],
    },
]

CENT = Decimal("0.01")


def money(value: Decimal) -> str:
    return str(value.quantize(CENT, rounding=ROUND_HALF_UP))


def compute_totals(lines) -> dict:
    line_totals = [(qty * price).quantize(CENT, ROUND_HALF_UP) for _, qty, _, price, _ in lines]
    by_rate: dict[Decimal, Decimal] = {}
    for (_, _, _, _, rate), total in zip(lines, line_totals):
        by_rate[rate] = by_rate.get(rate, Decimal("0")) + total
    taxes = {
        rate: (basis * rate / 100).quantize(CENT, ROUND_HALF_UP) for rate, basis in by_rate.items()
    }
    total_ht = sum(line_totals)
    total_vat = sum(taxes.values())
    return {
        "line_totals": line_totals,
        "by_rate": by_rate,
        "taxes": taxes,
        "ht": total_ht,
        "vat": total_vat,
        "ttc": total_ht + total_vat,
    }


def build_cii_xml(supplier: dict, totals: dict, due: date) -> bytes:
    lines_xml = []
    for index, (desc, qty, unit, price, rate) in enumerate(supplier["lines"], start=1):
        lines_xml.append(f"""
    <ram:IncludedSupplyChainTradeLineItem>
      <ram:AssociatedDocumentLineDocument>
        <ram:LineID>{index}</ram:LineID>
      </ram:AssociatedDocumentLineDocument>
      <ram:SpecifiedTradeProduct>
        <ram:Name>{escape(desc)}</ram:Name>
      </ram:SpecifiedTradeProduct>
      <ram:SpecifiedLineTradeAgreement>
        <ram:NetPriceProductTradePrice>
          <ram:ChargeAmount>{price}</ram:ChargeAmount>
        </ram:NetPriceProductTradePrice>
      </ram:SpecifiedLineTradeAgreement>
      <ram:SpecifiedLineTradeDelivery>
        <ram:BilledQuantity unitCode="{unit}">{qty}</ram:BilledQuantity>
      </ram:SpecifiedLineTradeDelivery>
      <ram:SpecifiedLineTradeSettlement>
        <ram:ApplicableTradeTax>
          <ram:TypeCode>VAT</ram:TypeCode>
          <ram:CategoryCode>S</ram:CategoryCode>
          <ram:RateApplicablePercent>{rate}</ram:RateApplicablePercent>
        </ram:ApplicableTradeTax>
        <ram:SpecifiedTradeSettlementLineMonetarySummation>
          <ram:LineTotalAmount>{money(totals["line_totals"][index - 1])}</ram:LineTotalAmount>
        </ram:SpecifiedTradeSettlementLineMonetarySummation>
      </ram:SpecifiedLineTradeSettlement>
    </ram:IncludedSupplyChainTradeLineItem>""")

    taxes_xml = []
    for rate, basis in sorted(totals["by_rate"].items()):
        taxes_xml.append(f"""
      <ram:ApplicableTradeTax>
        <ram:CalculatedAmount>{money(totals["taxes"][rate])}</ram:CalculatedAmount>
        <ram:TypeCode>VAT</ram:TypeCode>
        <ram:BasisAmount>{money(basis)}</ram:BasisAmount>
        <ram:CategoryCode>S</ram:CategoryCode>
        <ram:RateApplicablePercent>{rate}</ram:RateApplicablePercent>
      </ram:ApplicableTradeTax>""")

    s_line1, s_zip, s_city = supplier["address"]
    b_line1, b_zip, b_city = BUYER["address"]
    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<rsm:CrossIndustryInvoice
    xmlns:rsm="urn:un:unece:uncefact:data:standard:CrossIndustryInvoice:100"
    xmlns:ram="urn:un:unece:uncefact:data:standard:ReusableAggregateBusinessInformationEntity:100"
    xmlns:udt="urn:un:unece:uncefact:data:standard:UnqualifiedDataType:100">
  <rsm:ExchangedDocumentContext>
    <ram:GuidelineSpecifiedDocumentContextParameter>
      <ram:ID>urn:cen.eu:en16931:2017</ram:ID>
    </ram:GuidelineSpecifiedDocumentContextParameter>
  </rsm:ExchangedDocumentContext>
  <rsm:ExchangedDocument>
    <ram:ID>{supplier["number"]}</ram:ID>
    <ram:TypeCode>380</ram:TypeCode>
    <ram:IssueDateTime>
      <udt:DateTimeString format="102">{supplier["issue"]:%Y%m%d}</udt:DateTimeString>
    </ram:IssueDateTime>
  </rsm:ExchangedDocument>
  <rsm:SupplyChainTradeTransaction>{"".join(lines_xml)}
    <ram:ApplicableHeaderTradeAgreement>
      <ram:SellerTradeParty>
        <ram:Name>{escape(supplier["name"])}</ram:Name>
        <ram:SpecifiedLegalOrganization>
          <ram:ID schemeID="0002">{supplier["siren"]}</ram:ID>
        </ram:SpecifiedLegalOrganization>
        <ram:PostalTradeAddress>
          <ram:PostcodeCode>{s_zip}</ram:PostcodeCode>
          <ram:LineOne>{escape(s_line1)}</ram:LineOne>
          <ram:CityName>{escape(s_city)}</ram:CityName>
          <ram:CountryID>FR</ram:CountryID>
        </ram:PostalTradeAddress>
        <ram:SpecifiedTaxRegistration>
          <ram:ID schemeID="VA">{supplier["vat"]}</ram:ID>
        </ram:SpecifiedTaxRegistration>
      </ram:SellerTradeParty>
      <ram:BuyerTradeParty>
        <ram:Name>{escape(BUYER["name"])}</ram:Name>
        <ram:PostalTradeAddress>
          <ram:PostcodeCode>{b_zip}</ram:PostcodeCode>
          <ram:LineOne>{escape(b_line1)}</ram:LineOne>
          <ram:CityName>{escape(b_city)}</ram:CityName>
          <ram:CountryID>FR</ram:CountryID>
        </ram:PostalTradeAddress>
      </ram:BuyerTradeParty>
    </ram:ApplicableHeaderTradeAgreement>
    <ram:ApplicableHeaderTradeDelivery/>
    <ram:ApplicableHeaderTradeSettlement>
      <ram:InvoiceCurrencyCode>EUR</ram:InvoiceCurrencyCode>{"".join(taxes_xml)}
      <ram:SpecifiedTradePaymentTerms>
        <ram:DueDateDateTime>
          <udt:DateTimeString format="102">{due:%Y%m%d}</udt:DateTimeString>
        </ram:DueDateDateTime>
      </ram:SpecifiedTradePaymentTerms>
      <ram:SpecifiedTradeSettlementHeaderMonetarySummation>
        <ram:LineTotalAmount>{money(totals["ht"])}</ram:LineTotalAmount>
        <ram:TaxBasisTotalAmount>{money(totals["ht"])}</ram:TaxBasisTotalAmount>
        <ram:TaxTotalAmount currencyID="EUR">{money(totals["vat"])}</ram:TaxTotalAmount>
        <ram:GrandTotalAmount>{money(totals["ttc"])}</ram:GrandTotalAmount>
        <ram:DuePayableAmount>{money(totals["ttc"])}</ram:DuePayableAmount>
      </ram:SpecifiedTradeSettlementHeaderMonetarySummation>
    </ram:ApplicableHeaderTradeSettlement>
  </rsm:SupplyChainTradeTransaction>
</rsm:CrossIndustryInvoice>
"""
    return xml.encode("utf-8")


def build_pdf(supplier: dict, totals: dict, due: date) -> bytes:
    buffer = BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4
    x, y = 20 * mm, height - 25 * mm

    pdf.setFont("Helvetica-Bold", 14)
    pdf.drawString(x, y, supplier["name"])
    pdf.setFont("Helvetica", 9)
    line1, zipcode, city = supplier["address"]
    pdf.drawString(x, y - 5 * mm, f"{line1}, {zipcode} {city}")
    pdf.drawString(x, y - 10 * mm, f"SIREN {supplier['siren']} — TVA {supplier['vat']}")

    pdf.setFont("Helvetica-Bold", 12)
    pdf.drawRightString(width - 20 * mm, y, f"FACTURE {supplier['number']}")
    pdf.setFont("Helvetica", 9)
    pdf.drawRightString(width - 20 * mm, y - 5 * mm, f"Émise le {supplier['issue']:%d/%m/%Y}")
    pdf.drawRightString(width - 20 * mm, y - 10 * mm, f"Échéance le {due:%d/%m/%Y}")

    y -= 25 * mm
    pdf.setFont("Helvetica-Bold", 10)
    pdf.drawString(x, y, "Facturé à :")
    pdf.setFont("Helvetica", 9)
    b_line1, b_zip, b_city = BUYER["address"]
    pdf.drawString(x, y - 5 * mm, BUYER["name"])
    pdf.drawString(x, y - 10 * mm, f"{b_line1}, {b_zip} {b_city}")

    y -= 22 * mm
    pdf.setFont("Helvetica-Bold", 9)
    for label, offset in (
        ("Désignation", 0),
        ("Qté", 95),
        ("PU HT", 115),
        ("HT", 140),
        ("TVA", 162),
    ):
        pdf.drawString(x + offset * mm, y, label)
    pdf.line(x, y - 2 * mm, width - 20 * mm, y - 2 * mm)
    pdf.setFont("Helvetica", 9)
    y -= 8 * mm
    for (desc, qty, _, price, rate), line_total in zip(supplier["lines"], totals["line_totals"]):
        pdf.drawString(x, y, desc[:60])
        pdf.drawRightString(x + 105 * mm, y, f"{qty}")
        pdf.drawRightString(x + 132 * mm, y, f"{price} €")
        pdf.drawRightString(x + 155 * mm, y, f"{money(line_total)} €")
        pdf.drawRightString(x + 170 * mm, y, f"{rate} %")
        y -= 6 * mm

    y -= 6 * mm
    pdf.line(x + 100 * mm, y + 3 * mm, width - 20 * mm, y + 3 * mm)
    pdf.setFont("Helvetica", 10)
    pdf.drawRightString(x + 155 * mm, y - 2 * mm, "Total HT :")
    pdf.drawRightString(width - 20 * mm, y - 2 * mm, f"{money(totals['ht'])} €")
    pdf.drawRightString(x + 155 * mm, y - 8 * mm, "TVA :")
    pdf.drawRightString(width - 20 * mm, y - 8 * mm, f"{money(totals['vat'])} €")
    pdf.setFont("Helvetica-Bold", 11)
    pdf.drawRightString(x + 155 * mm, y - 15 * mm, "Total TTC :")
    pdf.drawRightString(width - 20 * mm, y - 15 * mm, f"{money(totals['ttc'])} €")

    pdf.setFont("Helvetica-Oblique", 7)
    pdf.drawString(
        x,
        15 * mm,
        "Document synthétique généré pour le POC AtelIA — ne constitue pas une facture réelle.",
    )
    pdf.showPage()
    pdf.save()
    return buffer.getvalue()


def main() -> None:
    SAMPLES_DIR.mkdir(exist_ok=True)
    for supplier in SUPPLIERS:
        totals = compute_totals(supplier["lines"])
        due = supplier["issue"] + timedelta(days=30)
        xml_bytes = build_cii_xml(supplier, totals, due)
        pdf_bytes = build_pdf(supplier, totals, due)
        facturx_pdf = generate_from_binary(pdf_bytes, xml_bytes)
        target = SAMPLES_DIR / f"facture_{supplier['slug']}_{supplier['number']}.pdf"
        target.write_bytes(facturx_pdf)
        print(f"OK  {target.name}  HT {money(totals['ht'])} €  TTC {money(totals['ttc'])} €")


if __name__ == "__main__":
    main()
