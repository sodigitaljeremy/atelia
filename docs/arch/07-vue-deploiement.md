# Vue déploiement

## Conteneurs

`docker-compose.yml` (fichier de prod) :

- **api** — image construite depuis le `Dockerfile` (python:3.12-slim + uv, `uvicorn
  app.core.main:app`, samples embarqués). Pas de port publié : le reverse proxy expose le
  port interne **8000**. Healthcheck compose sur `/health` (API + Postgres + extension pgvector),
  via `python -c urllib` (pas de curl dans l'image slim).
- **db** — `pgvector/pgvector:pg16`, jamais publié, volume persistant `pgdata`,
  healthcheck `pg_isready`.

En local, `docker-compose.override.yml` (chargé automatiquement par `docker compose up`)
publie `8000:8000` ; Coolify lance explicitement le fichier de base et l'ignore.

## Production

- **Hébergement** : VPS Hetzner, orchestré par **Coolify** (ressource Docker Compose).
- **Déploiement** : automatique à chaque push sur `main`. Le healthcheck `/health` conditionne
  la bascule du trafic.
- **Domaine** : **atel-ia.fr**, TLS géré par le proxy de Coolify (Traefik).
- **Secrets** : variables d'environnement via l'UI Coolify (`MISTRAL_API_KEY`,
  `POSTGRES_PASSWORD`, `DEMO_MODE`, `LLM_MODEL`/`EMBED_MODEL`). Jamais commitées
  (`.env` local gitignoré).
- **Démarrage applicatif** : le lifespan applique les `schema.sql` idempotents de chaque module
  puis leurs hooks `on_startup` (backfill des gains M1 ; ingestion du corpus M2 par empreinte
  de contenu — la prod se ré-indexe seule quand le corpus ou son nettoyage change) — pas
  d'étape de migration séparée.

## Pièges connus

- Postgres fige `POSTGRES_PASSWORD` à la première initialisation du volume `pgdata` : changer la
  variable ensuite exige `ALTER USER atelia WITH PASSWORD '…'` (ou la recréation du volume).
- Les samples étant embarqués dans l'image, les régénérer implique un rebuild.
