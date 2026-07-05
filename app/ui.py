"""Écrans opérateur (Jinja2 + HTMX) : validation humaine et dashboard de gains."""

from datetime import datetime
from decimal import Decimal, InvalidOperation

from fastapi import APIRouter, Form, HTTPException, Request, UploadFile
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates

from app import repository, services
from app.extraction import ExtractionError

router = APIRouter(include_in_schema=False)
templates = Jinja2Templates(directory="templates")


def _fmt_eur(value) -> str:
    if value is None:
        return "—"
    return f"{value:,.2f}".replace(",", " ").replace(".", ",") + " €"


def _fmt_qty(value) -> str:
    if value is None:
        return "—"
    text = f"{value:.3f}".rstrip("0").rstrip(".")
    return text.replace(".", ",")


templates.env.filters["eur"] = _fmt_eur
templates.env.filters["qty"] = _fmt_qty


def _to_date(value: str | None):
    return datetime.strptime(value, "%Y-%m-%d").date() if value else None


def _to_decimal(value: str | None):
    if not value:
        return None
    try:
        return Decimal(value.replace(",", ".").replace(" ", ""))
    except InvalidOperation as exc:
        raise HTTPException(status_code=400, detail=f"Montant invalide : {value}") from exc


@router.get("/")
async def home():
    return RedirectResponse("/invoices")


@router.get("/invoices")
async def invoices_list(request: Request, error: str | None = None):
    pending = await repository.list_invoices("en_validation")
    metrics = await repository.gains_metrics()
    return templates.TemplateResponse(
        request,
        "invoices_list.html",
        {"pending": pending, "metrics": metrics, "error": error, "active": "invoices"},
    )


@router.post("/invoices/upload")
async def invoices_upload(file: UploadFile):
    pdf_bytes = await file.read()
    try:
        invoice_id = await services.ingest_pdf(pdf_bytes)
    except ExtractionError as exc:
        return RedirectResponse(f"/invoices?error={exc}", status_code=303)
    return RedirectResponse(f"/invoices/{invoice_id}", status_code=303)


@router.get("/invoices/{invoice_id}")
async def invoice_detail(request: Request, invoice_id: int):
    invoice = await repository.get_invoice(invoice_id)
    if invoice is None:
        raise HTTPException(status_code=404, detail="Facture introuvable")
    lines = await repository.get_lines(invoice_id)
    return templates.TemplateResponse(
        request,
        "invoice_detail.html",
        {"invoice": invoice, "lines": lines, "active": "invoices"},
    )


@router.post("/invoices/{invoice_id}/validate")
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
):
    """Applique les corrections de l'opérateur puis valide (contrôle humain, ADR-005)."""
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


@router.post("/invoices/{invoice_id}/reject")
async def invoice_reject(invoice_id: int):
    if not await repository.set_status(invoice_id, "rejetee"):
        raise HTTPException(status_code=404, detail="Facture introuvable")
    return RedirectResponse("/invoices", status_code=303)


@router.get("/dashboard")
async def dashboard(request: Request):
    metrics = await repository.gains_metrics()
    return templates.TemplateResponse(
        request, "dashboard.html", {"metrics": metrics, "active": "dashboard"}
    )
