"""Requêtes SQL (asyncpg, sans ORM : 2 tables, mapping direct)."""

import json
from decimal import Decimal

import asyncpg

from app.core import db

# Hypothèses de gain affichées sur le dashboard (réf. brief : ~26 €/facture papier)
MINUTES_SAVED_PER_INVOICE = 5
COST_AVOIDED_PER_INVOICE_EUR = 26

HEADER_FIELDS = (
    "supplier_name",
    "supplier_siren",
    "invoice_number",
    "issue_date",
    "due_date",
    "currency",
    "total_ht",
    "total_vat",
    "total_ttc",
)


def decode_checks(record) -> dict:
    """Record asyncpg → dict avec les colonnes JSONB décodées (anomalies, compliance)."""
    data = dict(record)
    for field in ("anomalies", "compliance"):
        if isinstance(data.get(field), str):
            data[field] = json.loads(data[field])
    return data


async def find_duplicate(supplier_siren: str | None, invoice_number: str | None):
    """Facture non rejetée portant le même SIREN + numéro (détection de doublon)."""
    if not supplier_siren or not invoice_number:
        return None
    async with db.pool.acquire() as conn:
        return await conn.fetchrow(
            """
            SELECT id, invoice_number FROM invoice
            WHERE supplier_siren = $1 AND invoice_number = $2 AND status != 'rejetee'
            ORDER BY id LIMIT 1
            """,
            supplier_siren,
            invoice_number,
        )


async def create_invoice(
    header: dict,
    lines: list[dict],
    raw_xml: str,
    anomalies: list[dict] | None = None,
    compliance: list[dict] | None = None,
    is_duplicate: bool = False,
) -> int:
    """Insère entête + lignes + contrôles en une transaction, statut 'en_validation'."""
    async with db.pool.acquire() as conn:
        async with conn.transaction():
            invoice_id = await conn.fetchval(
                """
                INSERT INTO invoice (source, profile, supplier_name, supplier_siren,
                                     invoice_number, issue_date, due_date, currency,
                                     total_ht, total_vat, total_ttc, confidence, raw_xml,
                                     anomalies, compliance, is_duplicate)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13,
                        $14::jsonb, $15::jsonb, $16)
                RETURNING id
                """,
                header["source"],
                header["profile"],
                header["supplier_name"],
                header["supplier_siren"],
                header["invoice_number"],
                header["issue_date"],
                header["due_date"],
                header["currency"],
                header["total_ht"],
                header["total_vat"],
                header["total_ttc"],
                header["confidence"],
                raw_xml,
                json.dumps(anomalies or []),
                json.dumps(compliance or []),
                is_duplicate,
            )
            await conn.executemany(
                """
                INSERT INTO invoice_line (invoice_id, line_number, description, quantity,
                                          unit_price, line_amount_ht, vat_rate)
                VALUES ($1, $2, $3, $4, $5, $6, $7)
                """,
                [
                    (
                        invoice_id,
                        line["line_number"],
                        line["description"],
                        line["quantity"],
                        line["unit_price"],
                        line["line_amount_ht"],
                        line["vat_rate"],
                    )
                    for line in lines
                ],
            )
    return invoice_id


async def list_invoices(status: str | None = None) -> list[asyncpg.Record]:
    query = "SELECT * FROM invoice"
    args = []
    if status is not None:
        query += " WHERE status = $1"
        args.append(status)
    query += " ORDER BY created_at DESC"
    async with db.pool.acquire() as conn:
        return await conn.fetch(query, *args)


async def get_invoice(invoice_id: int) -> asyncpg.Record | None:
    async with db.pool.acquire() as conn:
        return await conn.fetchrow("SELECT * FROM invoice WHERE id = $1", invoice_id)


async def get_lines(invoice_id: int) -> list[asyncpg.Record]:
    async with db.pool.acquire() as conn:
        return await conn.fetch(
            "SELECT * FROM invoice_line WHERE invoice_id = $1 ORDER BY line_number",
            invoice_id,
        )


async def set_status(invoice_id: int, status: str, header_updates: dict | None = None) -> bool:
    """Passe une facture à `status`, en appliquant d'abord les corrections opérateur.

    C'est l'unique chemin d'écriture après ingestion : la validation humaine
    est bloquante par construction (ADR-005).
    """
    updates = {k: v for k, v in (header_updates or {}).items() if k in HEADER_FIELDS}
    assignments = ["status = $2", "updated_at = now()"]
    args: list = [invoice_id, status]
    for field, value in updates.items():
        args.append(value)
        assignments.append(f"{field} = ${len(args)}")
    async with db.pool.acquire() as conn:
        result = await conn.execute(
            f"UPDATE invoice SET {', '.join(assignments)} WHERE id = $1", *args
        )
    return result == "UPDATE 1"


async def gains_metrics() -> dict:
    """Métrique de gain : factures validées → heures économisées + coût évité."""
    async with db.pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT
                count(*) FILTER (WHERE status = 'validee')       AS validated,
                count(*) FILTER (WHERE status = 'en_validation') AS pending,
                count(*) FILTER (WHERE status = 'rejetee')       AS rejected,
                coalesce(sum(jsonb_array_length(anomalies)), 0)  AS anomalies_detected,
                count(*) FILTER (WHERE is_duplicate)             AS duplicates_flagged
            FROM invoice
            """
        )
    validated = row["validated"]
    return {
        "validated": validated,
        "pending": row["pending"],
        "rejected": row["rejected"],
        "anomalies_detected": row["anomalies_detected"],
        "duplicates_flagged": row["duplicates_flagged"],
        "hours_saved": (Decimal(validated * MINUTES_SAVED_PER_INVOICE) / 60).quantize(
            Decimal("0.01")
        ),
        "cost_avoided_eur": validated * COST_AVOIDED_PER_INVOICE_EUR,
        "minutes_per_invoice": MINUTES_SAVED_PER_INVOICE,
        "cost_per_invoice_eur": COST_AVOIDED_PER_INVOICE_EUR,
    }
