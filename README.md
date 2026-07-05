# AtelIA

Atelier IA de la Conserverie du Sud — POC d'automatisation de la facture électronique, **souverain** (Mistral, self-hosté, données synthétiques/publiques uniquement).

Contexte complet : [docs/brief.md](docs/brief.md).

## Stack

FastAPI · PostgreSQL + pgvector · LiteLLM → Mistral (`mistral-large`, `mistral-embed`), swappable vers Claude en config · Docker.

## Lancement

```bash
cp .env.example .env   # puis renseigner MISTRAL_API_KEY
docker compose up --build
```

Vérifier :

- `curl http://localhost:8000/health` → `200` (API + Postgres + extension pgvector)
- `curl http://localhost:8000/llm/ping` → appel test chat + embedding via Mistral (latence et tokens inclus)
- Docs interactives : http://localhost:8000/docs

## Démo M1 (happy path)

Des factures Factur-X synthétiques (profil EN 16931) sont fournies dans `samples/`
(régénérables : `uv run scripts/generate_samples.py`).

1. Ouvrir http://localhost:8000/invoices et déposer un PDF de `samples/`
2. L'extraction est **déterministe** (XML CII embarqué, aucun LLM) : entête + lignes s'affichent
3. Contrôler/corriger les champs puis **Valider** — aucune écriture sans validation humaine
4. Le dashboard http://localhost:8000/dashboard affiche le gain (≈ 5 min et 26 € économisés par facture validée)

Ingestion côté ERP : `curl -F "file=@samples/<facture>.pdf" http://localhost:8000/api/invoices`

## État d'avancement (tranches verticales)

- [x] **Slice 0 — Socle** : FastAPI + Postgres/pgvector + couche LLM (LiteLLM/Mistral) + Docker + healthcheck
- [x] **Slice 1 — M1 happy path** : facture Factur-X → extraction déterministe → écran de validation humaine → métrique de gain
- [ ] Slice 2 — M1 robustesse : anomalies, doublons, enrichissement Sirene
- [ ] Slice 3 — M2 RAG conformité (réponses sourcées)
- [ ] Slice 4 — Bonus (Open Food Facts, polish UI)
