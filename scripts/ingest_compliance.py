"""Ingestion manuelle du corpus conformité (idempotente — relançable sans doublon).

Lancement local : uv run python scripts/ingest_compliance.py
Dans le conteneur : docker compose exec api uv run --no-sync python scripts/ingest_compliance.py
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.core import db  # noqa: E402
from app.modules.compliance import repository  # noqa: E402


async def main() -> None:
    await db.connect()
    try:
        report = await repository.ingest_corpus()
        print(
            f"Ingestion : {report['documents']} document(s) — "
            f"{report['regenerated']} régénéré(s) ({report['chunks_added']} chunks), "
            f"{report['unchanged']} inchangé(s)."
        )
    finally:
        await db.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
