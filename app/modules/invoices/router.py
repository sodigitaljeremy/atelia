"""Routes du module Factures : écrans opérateur (Jinja2 + HTMX) et API JSON « prête ERP »."""

from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

from fastapi import APIRouter, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, RedirectResponse

from app.core.templates import module_templates
from app.modules.invoices import checks, repository, services
from app.modules.invoices.extraction import ExtractionError

templates = module_templates(Path(__file__).parent / "templates")

router = APIRouter()
ui = APIRouter(include_in_schema=False)
api = APIRouter(prefix="/api/invoices", tags=["invoices"])


# --- Écrans opérateur -------------------------------------------------------


def _to_date(value: str | None):
    return datetime.strptime(value, "%Y-%m-%d").date() if value else None


def _to_decimal(value: str | None):
    if not value:
        return None
    try:
        return Decimal(value.replace(",", ".").replace(" ", ""))
    except InvalidOperation as exc:
        raise HTTPException(status_code=400, detail=f"Montant invalide : {value}") from exc


@ui.get("/invoices")
async def invoices_list(request: Request, error: str | None = None):
    pending = await repository.list_invoices("en_validation")
    metrics = await repository.gains_metrics()
    samples = sorted(p.name for p in Path("samples").glob("*.pdf"))
    return templates.TemplateResponse(
        request,
        "invoices_list.html",
        {
            "pending": pending,
            "metrics": metrics,
            "error": error,
            "samples": samples,
            "active": "invoices",
        },
    )


@ui.get("/samples/{filename}")
async def sample_download(filename: str):
    """Téléchargement forcé d'une facture d'exemple (Content-Disposition: attachment)."""
    if filename not in {p.name for p in Path("samples").glob("*.pdf")}:
        raise HTTPException(status_code=404, detail="Exemple introuvable")
    return FileResponse(Path("samples") / filename, media_type="application/pdf", filename=filename)


@ui.post("/invoices/upload")
async def invoices_upload(file: UploadFile):
    pdf_bytes = await file.read()
    try:
        invoice_id = await services.ingest_pdf(pdf_bytes)
    except ExtractionError as exc:
        return RedirectResponse(f"/invoices?error={exc}", status_code=303)
    return RedirectResponse(f"/invoices/{invoice_id}", status_code=303)


@ui.get("/invoices/{invoice_id}")
async def invoice_detail(request: Request, invoice_id: int, error: str | None = None):
    invoice = await repository.get_invoice(invoice_id)
    if invoice is None:
        raise HTTPException(status_code=404, detail="Facture introuvable")
    invoice = repository.decode_checks(invoice)
    lines = await repository.get_lines(invoice_id)
    return templates.TemplateResponse(
        request,
        "invoice_detail.html",
        {
            "invoice": invoice,
            "lines": lines,
            "error": error,
            "has_blocking": checks.has_blocking(invoice["anomalies"]),
            "active": "invoices",
        },
    )


@ui.post("/invoices/{invoice_id}/validate")
async def invoice_validate(
    invoice_id: int,
    supplier_name: str = Form(""),
    supplier_siren: str = Form(""),
    invoice_number: str = Form(""),
    issue_date: str = Form(""),
    due_date: str = Form(""),
    currency: str = Form("EUR"),
    total_ht: str = Form(""),
    total_vat: str = Form(""),
    total_ttc: str = Form(""),
    confirm_blocking: str = Form(""),
):
    """Applique les corrections de l'opérateur puis valide (contrôle humain, ADR-005).

    Si la facture porte une anomalie bloquante (ou un doublon), la validation exige
    une confirmation explicite — vérifiée ici côté serveur, pas seulement dans l'UI.
    """
    invoice = await repository.get_invoice(invoice_id)
    if invoice is None:
        raise HTTPException(status_code=404, detail="Facture introuvable")
    if checks.has_blocking(repository.decode_checks(invoice)["anomalies"]) and not confirm_blocking:
        return RedirectResponse(
            f"/invoices/{invoice_id}?error=Cette facture porte un contrôle bloquant : "
            "cochez la confirmation explicite pour pouvoir la valider.",
            status_code=303,
        )
    updates = {
        "supplier_name": supplier_name or None,
        "supplier_siren": supplier_siren or None,
        "invoice_number": invoice_number or None,
        "issue_date": _to_date(issue_date),
        "due_date": _to_date(due_date),
        "currency": currency or "EUR",
        "total_ht": _to_decimal(total_ht),
        "total_vat": _to_decimal(total_vat),
        "total_ttc": _to_decimal(total_ttc),
    }
    if not await repository.set_status(invoice_id, "validee", updates):
        raise HTTPException(status_code=404, detail="Facture introuvable")
    return RedirectResponse("/dashboard", status_code=303)


@ui.post("/invoices/{invoice_id}/reject")
async def invoice_reject(invoice_id: int):
    if not await repository.set_status(invoice_id, "rejetee"):
        raise HTTPException(status_code=404, detail="Facture introuvable")
    return RedirectResponse("/invoices", status_code=303)


@ui.get("/dashboard")
async def dashboard(request: Request):
    metrics = await repository.gains_metrics()
    return templates.TemplateResponse(
        request, "dashboard.html", {"metrics": metrics, "active": "dashboard"}
    )


# --- API JSON — le point d'entrée « prêt à brancher sur votre ERP » ---------


def _serialize(record) -> dict:
    data = repository.decode_checks(record)
    data.pop("raw_xml", None)
    return data


@api.post("", status_code=201)
async def ingest_invoice(file: UploadFile):
    pdf_bytes = await file.read()
    try:
        invoice_id = await services.ingest_pdf(pdf_bytes)
    except ExtractionError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    invoice = await repository.get_invoice(invoice_id)
    lines = await repository.get_lines(invoice_id)
    return {"invoice": _serialize(invoice), "lines": [dict(line) for line in lines]}


@api.get("")
async def list_invoices(status: str | None = None):
    return [_serialize(record) for record in await repository.list_invoices(status)]


@api.get("/{invoice_id}")
async def get_invoice(invoice_id: int):
    invoice = await repository.get_invoice(invoice_id)
    if invoice is None:
        raise HTTPException(status_code=404, detail="Facture introuvable")
    lines = await repository.get_lines(invoice_id)
    return {"invoice": _serialize(invoice), "lines": [dict(line) for line in lines]}


router.include_router(ui)
router.include_router(api)
