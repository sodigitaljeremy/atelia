# CLAUDE.md — AtelIA

## Projet
- AtelIA = plateforme de démonstration AI Engineering (portfolio), incarnant une **PME agroalimentaire fictive**.
- But : prouver l'intégration de l'IA en entreprise sur de la vraie donnée, avec **la bonne technique par problème**.
- **Source de vérité (contexte + roadmap) : `docs/brief-v2.md`** — le lire avant toute tâche d'architecture.
- En prod : atel-ia.fr (Coolify/Hetzner, **auto-deploy sur push `main`**).

## Stack
- Python 3.12 · FastAPI · PostgreSQL + pgvector · LiteLLM → Mistral (`mistral-large`, `mistral-embed`)
- Frontend léger : Jinja2 + HTMX
- Dépendances : **uv** (`pyproject.toml`) — jamais `pip`
- Conteneurs : Docker / docker-compose · déploiement Coolify

## Commandes
- Installer : `uv sync`
- Lancer en local : `docker compose up --build` (l'override publie le port 8000 en local)
- Santé : `curl localhost:8000/health` → 200
- Factures de test : `uv run scripts/generate_samples.py`
- Lint / format (avant commit) : `uv run ruff check .` puis `uv run ruff format .`

## Carte du code (cible v2)
- `app/core/` : config · db (pool + application des schémas) · llm (LiteLLM) · registry (modules) · main (factory)
- `app/modules/<nom>/` : un module = router + logique + `schema.sql` (idempotent) + templates
- `app/shared/templates/` : `base.html`, `home.html` (hub), `about.html`
- `docs/` : `brief.md` (v1), `brief-v2.md` (roadmap), arc42 (à venir), ADR
- Chaque module **possède ses tables** (schema idempotent, appliqué au démarrage).

## Méthode de travail — IMPORTANT
- **Plan avant code** : proposer un plan et **attendre ma validation** avant d'implémenter.
- **Une tranche verticale à la fois** : ne coder QUE le périmètre demandé. Si tu débordes, t'arrêter.
- **Preuve d'exécution** : ne jamais dire « c'est fait » sans avoir lancé le test réel et montré la sortie.
- **Condition d'arrêt** : chaque slice finit déployable/démontrable, puis **commit atomique**.
- **Non-régression** : après un refactor, prouver que l'existant marche toujours (ex. parcours facture).
- Ne pas réécrire ce qui existe sans raison : d'abord `git status` / `git diff` pour l'état des lieux.

## Principes produit (non négociables, à respecter dans le code)
- **Souveraineté** : Mistral par défaut via `app/core/llm`, swappable Claude en config. Tout appel LLM passe par cette couche.
- **Bonne technique par problème** : déterministe quand c'est fiable (pas de LLM inutile), RAG pour le documentaire, agent pour l'orchestration.
- **Human-in-the-loop** : aucune écriture / décision engageante sans validation d'un opérateur.
- **Données** : publiques (API officielles) + synthétiques **uniquement**. JAMAIS de donnée privée réelle.
- **Anonymisation** : PME fictive, aucune entreprise réelle nommée. Relire avant chaque déploiement.
- **Anti-over-engineering** : MVP démontrable d'abord, raffinement ensuite.

## Conventions
- Langue : **tout en français** (commentaires, UI, commits, docs).
- Doc-as-code : ADR pour les décisions structurantes, arc42 pour l'architecture.
- Secrets : en variables d'environnement (`.env` local gitignore, UI Coolify en prod). Jamais commités.
- Git : HTTPS via `gh` CLI (compte `sodigitaljeremy`). Commits atomiques par tranche, message clair.

## Ne PAS faire
- Ne pas exposer le port Postgres (5432) publiquement.
- Ne pas coder plusieurs modules en parallèle.
- Ne pas mettre de règles de style ici : le linter (ruff) s'en charge.
- Ne pas déployer sans avoir relu l'anonymisation.