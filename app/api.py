"""API JSON — le point d'entrée « prêt à brancher sur votre ERP »."""

from fastapi import APIRouter, HTTPException, UploadFile

from app import repository, services
from app.extraction import ExtractionError

router = APIRouter(prefix="/api/invoices", tags=["invoices"])


def _serialize(record) -> dict:
    data = dict(record)
    data.pop("raw_xml", None)
    return data


@router.post("", status_code=201)
async def ingest_invoice(file: UploadFile):
    pdf_bytes = await file.read()
    try:
        invoice_id = await services.ingest_pdf(pdf_bytes)
    except ExtractionError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    invoice = await repository.get_invoice(invoice_id)
    lines = await repository.get_lines(invoice_id)
    return {"invoice": _serialize(invoice), "lines": [dict(line) for line in lines]}


@router.get("")
async def list_invoices(status: str | None = None):
    return [_serialize(record) for record in await repository.list_invoices(status)]


@router.get("/{invoice_id}")
async def get_invoice(invoice_id: int):
    invoice = await repository.get_invoice(invoice_id)
    if invoice is None:
        raise HTTPException(status_code=404, detail="Facture introuvable")
    lines = await repository.get_lines(invoice_id)
    return {"invoice": _serialize(invoice), "lines": [dict(line) for line in lines]}
