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

## État d'avancement (tranches verticales)

- [x] **Slice 0 — Socle** : FastAPI + Postgres/pgvector + couche LLM (LiteLLM/Mistral) + Docker + healthcheck
- [ ] Slice 1 — M1 happy path : facture Factur-X → extraction → validation humaine → métrique de gain
- [ ] Slice 2 — M1 robustesse : anomalies, doublons, enrichissement Sirene
- [ ] Slice 3 — M2 RAG conformité (réponses sourcées)
- [ ] Slice 4 — Bonus (Open Food Facts, polish UI)
