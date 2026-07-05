# AtelIA

Atelier IA de la Conserverie du Sud — POC d'automatisation de la facture électronique, **souverain** (Mistral, self-hosté, données synthétiques/publiques uniquement).

Contexte complet : [docs/brief.md](docs/brief.md).

## Stack

FastAPI · PostgreSQL + pgvector · LiteLLM → Mistral (`mistral-large`, `mistral-embed`), swappable vers Claude en config · Docker.

## Lancement

```bash
cp .env.example .env   # puis renseigner MISTRAL_API_KEY et POSTGRES_PASSWORD
docker compose up --build
```

En local, `docker-compose.override.yml` (chargé automatiquement) publie le port
8000 vers l'hôte ; le fichier de base n'expose aucun port, c'est le reverse
proxy qui s'en charge en prod.

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

## Déploiement Coolify

1. Créer une ressource **Docker Compose** pointant sur ce dépôt (fichier :
   `docker-compose.yml` — l'override local n'est pas chargé, l'API ne publie
   donc aucun port hôte).
2. Définir les variables d'environnement :
   - `MISTRAL_API_KEY` (requis)
   - `POSTGRES_PASSWORD` (requis — valeur forte, le compose refuse de démarrer sans)
   - `LLM_MODEL` / `EMBED_MODEL` (optionnels, valeurs par défaut dans `.env.example`)
3. Exposer le service **`api`** sur son port interne **8000** (Traefik/Coolify
   gère le domaine et le TLS). Postgres reste interne au réseau compose,
   jamais publié.
4. Le service `api` a un healthcheck compose sur `/health` (API + Postgres +
   pgvector) : Coolify ne bascule le trafic que lorsqu'il passe au vert.
5. Les données Postgres persistent dans le volume `pgdata` ; les factures
   d'exemple sont embarquées dans l'image et téléchargeables depuis la page
   d'accueil pour tester la démo.

## État d'avancement (tranches verticales)

- [x] **Slice 0 — Socle** : FastAPI + Postgres/pgvector + couche LLM (LiteLLM/Mistral) + Docker + healthcheck
- [x] **Slice 1 — M1 happy path** : facture Factur-X → extraction déterministe → écran de validation humaine → métrique de gain
- [ ] Slice 2 — M1 robustesse : anomalies, doublons, enrichissement Sirene
- [ ] Slice 3 — M2 RAG conformité (réponses sourcées)
- [ ] Slice 4 — Bonus (Open Food Facts, polish UI)
