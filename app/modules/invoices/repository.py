"""Requêtes SQL (asyncpg, sans ORM : 2 tables, mapping direct)."""

import json
from decimal import Decimal

import asyncpg

from app.core import db
from app.core.config import settings

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


RATE_KEYS = ("minutes_saved_per_invoice", "cost_avoided_per_invoice_eur")


async def get_rates() -> dict:
    """Tarif courant : settings_runtime si réglé, sinon les défauts de la config.

    Ne vaut que pour les PROCHAINES validations — jamais appliqué rétroactivement.
    """
    async with db.pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT key, value FROM settings_runtime WHERE key = ANY($1)", list(RATE_KEYS)
        )
    values = {row["key"]: row["value"] for row in rows}
    return {
        "minutes": int(values.get("minutes_saved_per_invoice", settings.minutes_saved_per_invoice)),
        "cost": int(
            values.get("cost_avoided_per_invoice_eur", settings.cost_avoided_per_invoice_eur)
        ),
    }


async def set_rates(minutes: int, cost: int) -> None:
    """Persiste le tarif par défaut des prochaines validations (idempotent)."""
    async with db.pool.acquire() as conn:
        await conn.executemany(
            """
            INSERT INTO settings_runtime (key, value) VALUES ($1, $2)
            ON CONFLICT (key) DO UPDATE SET value = excluded.value, updated_at = now()
            """,
            [
                ("minutes_saved_per_invoice", str(minutes)),
                ("cost_avoided_per_invoice_eur", str(cost)),
            ],
        )


async def record_gain(invoice_id: int) -> None:
    """Acte le gain d'une validation dans le journal append-only (une seule fois par facture).

    Le tarif est figé DANS l'événement au moment de la validation : changer le tarif
    ensuite ne recalcule jamais le passé (auditabilité — la somme reste fidèle).
    """
    rates = await get_rates()
    async with db.pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO gain_event (invoice_id, minutes_saved, cost_avoided_eur)
            VALUES ($1, $2, $3)
            ON CONFLICT (invoice_id) DO NOTHING
            """,
            invoice_id,
            rates["minutes"],
            rates["cost"],
        )


async def backfill_gain_events() -> None:
    """Crée l'événement manquant pour les factures validées avant le journal (idempotent).

    `created_at` reprend `updated_at` de la facture (≈ date de validation) pour
    garder un historique daté cohérent. Relançable sans doublonner (UNIQUE invoice_id).
    """
    rates = await get_rates()
    async with db.pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO gain_event (invoice_id, minutes_saved, cost_avoided_eur, created_at)
            SELECT id, $1, $2, updated_at FROM invoice WHERE status = 'validee'
            ON CONFLICT (invoice_id) DO NOTHING
            """,
            rates["minutes"],
            rates["cost"],
        )


async def reset_demo() -> None:
    """Vide les données de démo du module Factures — et UNIQUEMENT elles.

    settings_runtime survit volontairement (le tarif réglé est une configuration,
    pas une donnée de démo). Protégé en amont par settings.demo_mode + confirmation.
    """
    async with db.pool.acquire() as conn:
        await conn.execute("TRUNCATE invoice, invoice_line, gain_event RESTART IDENTITY")


async def gains_metrics() -> dict:
    """Métriques du dashboard. Les gains viennent du journal gain_event (cumul
    append-only : rejeter une facture déjà validée ne fait PAS redescendre le cumul)."""
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
        gains = await conn.fetchrow(
            """
            SELECT count(*)                           AS events,
                   coalesce(sum(minutes_saved), 0)    AS minutes,
                   coalesce(sum(cost_avoided_eur), 0) AS cost
            FROM gain_event
            """
        )
    rates = await get_rates()
    return {
        "gain_events": gains["events"],
        "validated": row["validated"],
        "pending": row["pending"],
        "rejected": row["rejected"],
        "anomalies_detected": row["anomalies_detected"],
        "duplicates_flagged": row["duplicates_flagged"],
        "hours_saved": (Decimal(gains["minutes"]) / 60).quantize(Decimal("0.01")),
        "cost_avoided_eur": gains["cost"],
        "minutes_per_invoice": rates["minutes"],
        "cost_per_invoice_eur": rates["cost"],
    }


async def gains_history(limit: int = 10) -> list[asyncpg.Record]:
    """Derniers événements de gain, avec la facture associée (peut avoir disparu : LEFT JOIN)."""
    async with db.pool.acquire() as conn:
        return await conn.fetch(
            """
            SELECT g.created_at, g.minutes_saved, g.cost_avoided_eur,
                   i.invoice_number, i.supplier_name
            FROM gain_event g LEFT JOIN invoice i ON i.id = g.invoice_id
            ORDER BY g.created_at DESC, g.id DESC
            LIMIT $1
            """,
            limit,
        )


async def gains_timeline() -> list[asyncpg.Record]:
    """Coût évité agrégé par jour (ordre chronologique) — base de la courbe cumulée."""
    async with db.pool.acquire() as conn:
        return await conn.fetch(
            """
            SELECT created_at::date AS day, sum(cost_avoided_eur) AS cost
            FROM gain_event GROUP BY day ORDER BY day
            """
        )
