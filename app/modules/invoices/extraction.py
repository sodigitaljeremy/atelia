"""Extraction déterministe Factur-X : PDF/A-3 → données structurées.

Aucun LLM ici : le XML CII embarqué fait foi (lib factur-x + XPath).
Le fallback LLM pour PDF simple est prévu en Slice 2 — c'est là que
`source` et `confidence` prendront d'autres valeurs.
"""

import io
from datetime import date, datetime
from decimal import Decimal

from facturx import get_xml_from_pdf
from lxml import etree

NS = {
    "rsm": "urn:un:unece:uncefact:data:standard:CrossIndustryInvoice:100",
    "ram": "urn:un:unece:uncefact:data:standard:ReusableAggregateBusinessInformationEntity:100",
    "udt": "urn:un:unece:uncefact:data:standard:UnqualifiedDataType:100",
}

PROFILE_LABELS = {
    "urn:factur-x.eu:1p0:minimum": "MINIMUM",
    "urn:factur-x.eu:1p0:basicwl": "BASIC WL",
    "urn:cen.eu:en16931:2017#compliant#urn:factur-x.eu:1p0:basic": "BASIC",
    "urn:cen.eu:en16931:2017": "EN 16931",
}


class ExtractionError(Exception):
    """PDF sans XML Factur-X exploitable."""


def _text(node, xpath: str) -> str | None:
    found = node.xpath(xpath, namespaces=NS)
    if not found:
        return None
    value = found[0].text
    return value.strip() if value else None


def _decimal(node, xpath: str) -> Decimal | None:
    value = _text(node, xpath)
    return Decimal(value) if value is not None else None


def _date(node, xpath: str) -> date | None:
    value = _text(node, xpath)
    if value is None:
        return None
    return datetime.strptime(value, "%Y%m%d").date()  # format CII "102"


def extract_invoice(pdf_bytes: bytes) -> dict:
    """Retourne {header: dict, lines: list[dict], raw_xml: str} depuis un PDF Factur-X."""
    try:
        _, xml_bytes = get_xml_from_pdf(
            io.BytesIO(pdf_bytes), check_xsd=True, check_schematron=False
        )
    except Exception as exc:
        raise ExtractionError(f"XML Factur-X introuvable ou invalide : {exc}") from exc
    if not xml_bytes:
        raise ExtractionError("Aucun XML Factur-X embarqué dans ce PDF.")

    root = etree.fromstring(xml_bytes)

    guideline = _text(root, "//ram:GuidelineSpecifiedDocumentContextParameter/ram:ID") or ""
    seller = root.xpath("//ram:ApplicableHeaderTradeAgreement/ram:SellerTradeParty", namespaces=NS)
    seller = seller[0] if seller else root
    summation = root.xpath("//ram:SpecifiedTradeSettlementHeaderMonetarySummation", namespaces=NS)
    summation = summation[0] if summation else root

    header = {
        "source": "factur-x",
        "profile": PROFILE_LABELS.get(guideline, guideline),
        "supplier_name": _text(seller, "ram:Name"),
        "supplier_siren": _text(seller, "ram:SpecifiedLegalOrganization/ram:ID"),
        "invoice_number": _text(root, "//rsm:ExchangedDocument/ram:ID"),
        "issue_date": _date(root, "//rsm:ExchangedDocument/ram:IssueDateTime/udt:DateTimeString"),
        "due_date": _date(
            root, "//ram:SpecifiedTradePaymentTerms/ram:DueDateDateTime/udt:DateTimeString"
        ),
        "currency": _text(root, "//ram:InvoiceCurrencyCode") or "EUR",
        "total_ht": _decimal(summation, "ram:TaxBasisTotalAmount"),
        "total_vat": _decimal(summation, "ram:TaxTotalAmount"),
        "total_ttc": _decimal(summation, "ram:GrandTotalAmount"),
        "confidence": 1.0,  # extraction déterministe : le XML fait foi
    }

    lines = []
    for item in root.xpath("//ram:IncludedSupplyChainTradeLineItem", namespaces=NS):
        line_number = _text(item, "ram:AssociatedDocumentLineDocument/ram:LineID")
        lines.append(
            {
                "line_number": int(line_number) if line_number else len(lines) + 1,
                "description": _text(item, "ram:SpecifiedTradeProduct/ram:Name"),
                "quantity": _decimal(item, "ram:SpecifiedLineTradeDelivery/ram:BilledQuantity"),
                "unit_price": _decimal(
                    item,
                    "ram:SpecifiedLineTradeAgreement/ram:NetPriceProductTradePrice/ram:ChargeAmount",
                ),
                "line_amount_ht": _decimal(
                    item,
                    "ram:SpecifiedLineTradeSettlement"
                    "/ram:SpecifiedTradeSettlementLineMonetarySummation/ram:LineTotalAmount",
                ),
                "vat_rate": _decimal(
                    item,
                    "ram:SpecifiedLineTradeSettlement/ram:ApplicableTradeTax"
                    "/ram:RateApplicablePercent",
                ),
            }
        )

    return {"header": header, "lines": lines, "raw_xml": xml_bytes.decode("utf-8")}
