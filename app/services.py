"""Services partagés entre l'API JSON et l'UI."""

from app import repository
from app.extraction import extract_invoice


async def ingest_pdf(pdf_bytes: bytes) -> int:
    """Pipeline happy path : extraction Factur-X → stockage 'en_validation'.

    Lève ExtractionError si le PDF n'embarque pas de XML CII valide.
    """
    extracted = extract_invoice(pdf_bytes)
    return await repository.create_invoice(
        extracted["header"], extracted["lines"], extracted["raw_xml"]
    )
