"""Services partagés entre l'API JSON et l'UI."""

from app.modules.invoices import checks, repository
from app.modules.invoices.extraction import extract_invoice


async def ingest_pdf(pdf_bytes: bytes) -> int:
    """Pipeline d'ingestion : extraction Factur-X → contrôles déterministes → stockage.

    Les anomalies, la checklist conformité et le doublon éventuel sont calculés ici
    (aucun LLM) et stockés avec la facture, statut 'en_validation'.
    Lève ExtractionError si le PDF n'embarque pas de XML CII valide.
    """
    extracted = extract_invoice(pdf_bytes)
    header, lines = extracted["header"], extracted["lines"]

    anomalies = checks.check_anomalies(header, lines)
    compliance = checks.check_compliance(header)

    duplicate = await repository.find_duplicate(header["supplier_siren"], header["invoice_number"])
    if duplicate is not None:
        anomalies.insert(0, checks.duplicate_anomaly(duplicate["id"], duplicate["invoice_number"]))

    return await repository.create_invoice(
        header,
        lines,
        extracted["raw_xml"],
        anomalies=anomalies,
        compliance=compliance,
        is_duplicate=duplicate is not None,
    )
