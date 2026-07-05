"""Requêtes SQL (asyncpg, sans ORM : 2 tables, mapping direct)."""

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


async def create_invoice(header: dict, lines: list[dict], raw_xml: str) -> int:
    """Insère entête + lignes en une transaction, statut 'en_validation'. Retourne l'id."""
    async with db.pool.acquire() as conn:
        async with conn.transaction():
            invoice_id = await conn.fetchval(
                """
                INSERT INTO invoice (source, profile, supplier_name, supplier_siren,
                                     invoice_number, issue_date, due_date, currency,
                                     total_ht, total_vat, total_ttc, confidence, raw_xml)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13)
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
                count(*) FILTER (WHERE status = 'rejetee')       AS rejected
            FROM invoice
            """
        )
    validated = row["validated"]
    return {
        "validated": validated,
        "pending": row["pending"],
        "rejected": row["rejected"],
        "hours_saved": (Decimal(validated * MINUTES_SAVED_PER_INVOICE) / 60).quantize(
            Decimal("0.01")
        ),
        "cost_avoided_eur": validated * COST_AVOIDED_PER_INVOICE_EUR,
        "minutes_per_invoice": MINUTES_SAVED_PER_INVOICE,
        "cost_per_invoice_eur": COST_AVOIDED_PER_INVOICE_EUR,
    }
