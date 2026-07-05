# AtelIA — l'atelier IA d'une PME (fictive)

**Plateforme de démonstration AI Engineering** : des cas d'usage métier réels, résolus chacun
avec la technique adaptée — et jamais un LLM plaqué là où il n'apporte rien.

Démo live : **[atel-ia.fr](https://atel-ia.fr)** · Roadmap : [docs/brief-v2.md](docs/brief-v2.md) ·
Architecture : [docs/arch/](docs/arch/README.md)

## 1. Le problème

Intégrer l'IA dans une PME, ce n'est pas brancher un chatbot : c'est diagnostiquer un besoin
métier, choisir l'approche qui le résout au juste coût — **déterministe** quand la donnée est
structurée et fiable, **RAG** pour le documentaire, **agent** pour l'orchestration,
**classification** pour le non-structuré — et garder un humain dans la boucle dès qu'une
décision engage. C'est cette capacité de diagnostic que la plateforme démontre, sur pièce.

## 2. La plateforme et sa démarche

AtelIA incarne une PME agroalimentaire **fictive**, la « Conserverie du Val » (aucune entreprise
réelle nommée, nom paramétrable). Chaque module part d'un problème concret de cette PME, le
résout de bout en bout, et se mesure.

- **Souveraine** : modèles Mistral par défaut, self-hosté, swap vers Claude en une variable de config.
- **Human-in-the-loop** : aucune écriture ni décision engageante sans validation d'un opérateur.
- **Données sûres** : publiques (API et textes officiels) ou synthétiques — jamais de donnée privée réelle.
- **Toujours démontrable** : chaque tranche livrée est déployée ; la plateforme n'est jamais un chantier.

## 3. Les modules

### 🧾 Factures fournisseurs — livré

La saisie manuelle d'une facture papier coûte ~15 € et ~5 min ([France Num](https://www.francenum.gouv.fr/) ;
fourchette 14–20 € selon le rapport IGF/DGFiP sur la facturation électronique). Le module :

- **Extraction déterministe** du XML CII embarqué dans les PDF Factur-X (profil EN 16931) —
  zéro LLM : quand le standard fait foi, les règles suffisent et le résultat est exact à 100 %.
- **Contrôles automatiques à l'ingestion** : cohérence des totaux (tolérance d'arrondi), taux de
  TVA plausibles, dates (échéance incohérente ou déjà dépassée), montants, fournisseur étranger —
  chaque anomalie avec sa sévérité (bloquant / avertissement).
- **Doublons** : même fournisseur + même numéro déjà en base → signalé, validation sous
  confirmation explicite (vérifiée côté serveur).
- **Checklist conformité** : présence des mentions attendues (SIREN, numéro, dates, montants) —
  vérification factuelle, affichée avec son disclaimer : ce n'est pas un avis juridique.
- **Gains auditables** : journal d'événements **append-only** (un gain acté à chaque validation,
  jamais recalculé rétroactivement), historique daté, courbe cumulée, simulateur à curseurs et
  tarif paramétrable — les hypothèses sont affichées comme des estimations à calibrer.
- **Export ERP** : API JSON documentée (`POST /api/invoices` pour pousser un PDF,
  `GET /api/invoices?status=validee` pour ne récupérer que le validé par un humain).

9 factures de démo téléchargeables depuis l'UI, dont 3 volontairement incohérentes
(préfixe `anomalie_`) pour voir les contrôles réagir.

### À venir (cadrés dans le [brief v2](docs/brief-v2.md), non construits)

- **Assistant conformité** (M2) : RAG sourcé sur textes publics (INCO/allergènes, facturation
  électronique, HACCP) — citations obligatoires, « je ne sais pas » hors corpus.
- **Fiabilité fournisseurs** (M3) : agent en function-calling sur API publiques officielles
  (Recherche d'entreprises/Sirene, BODACC) → fiche enrichie + score expliqué.
- **Triage de flux entrants** (M4, option) : classification LLM de textes libres
  (catégorie, priorité, routage).

## 4. Architecture

Un **socle** (`app/core/`) héberge des **modules enfichables** (`app/modules/`), découverts par un
registre : un module = un package exposant son contrat (router UI+API, `schema.sql` idempotent
appliqué au démarrage, métadonnées de navigation, hook de démarrage optionnel). Le hub d'accueil
et la navigation se génèrent depuis ce registre — ajouter un module = déposer un dossier.
Détails : [vue des briques](docs/arch/05-vue-des-briques.md) · décisions :
[ADR-101…107](docs/arch/09-decisions-architecture.md).

## 5. Stack

Python 3.12 · FastAPI · PostgreSQL + **pgvector** · **LiteLLM** → Mistral
(`mistral-large`, `mistral-embed`), swappable Claude en config · Jinja2 + HTMX (pas de build
front) · uv · Docker/Compose · déployé via Coolify.

## 6. Démo live

**[atel-ia.fr](https://atel-ia.fr)** — téléchargez une facture d'exemple depuis la page Factures,
déposez-la, contrôlez, validez, regardez les gains bouger. C'est une démo publique : les données
sont synthétiques et réinitialisables.

## 7. Lancement local

```bash
cp .env.example .env   # renseigner MISTRAL_API_KEY et POSTGRES_PASSWORD
docker compose up --build
```

- UI : http://localhost:8000 · API : http://localhost:8000/docs
- `curl localhost:8000/health` → 200 (API + Postgres + pgvector) ·
  `curl localhost:8000/llm/ping` → test chat + embedding Mistral
- Tests et lint : `uv run pytest` · `uv run ruff check .`
- Samples régénérables : `uv run scripts/generate_samples.py` (valides) et
  `uv run scripts/generate_broken_samples.py` (incohérents exprès)

En local, `docker-compose.override.yml` (chargé automatiquement) publie le port 8000 ;
le fichier de base n'expose aucun port — en prod c'est le reverse proxy qui s'en charge.

## Déploiement Coolify

1. Ressource **Docker Compose** pointant sur ce dépôt (`docker-compose.yml` ; l'override local
   n'est pas chargé). Auto-deploy sur push `main`.
2. Variables d'environnement : `MISTRAL_API_KEY` (requis), `POSTGRES_PASSWORD` (requis, valeur
   forte — le compose refuse de démarrer sans), `DEMO_MODE=false` recommandé en prod (désactive
   le bouton de réinitialisation), `LLM_MODEL`/`EMBED_MODEL` optionnels.
3. Exposer le service **`api`** sur son port interne **8000** (Traefik/Coolify gère domaine et
   TLS). Postgres n'est jamais publié.
4. Healthcheck compose sur `/health` : le trafic ne bascule que lorsqu'il est vert.
5. Persistance : volume `pgdata`. Attention : Postgres fige `POSTGRES_PASSWORD` au premier
   démarrage du volume (changer la variable ensuite nécessite un `ALTER USER`).

## État d'avancement

- [x] Socle FastAPI + Postgres/pgvector + couche LLM (LiteLLM/Mistral) + Docker
- [x] Module Factures — happy path : extraction Factur-X déterministe, validation humaine, gains
- [x] Refactor plateforme : socle + modules + registre, hub, page Démarche, anonymisation
- [x] Module Factures — robustesse : anomalies, doublons, conformité, export ERP
- [x] Module Factures — démo complète, journal de gains append-only, hypothèses sourcées,
      simulateur, tarif runtime, reset démo
- [ ] M2 — Assistant conformité (RAG sourcé sur pgvector)
- [ ] M3 — Fiabilité fournisseurs (agent + API publiques)
- [ ] M4 — Triage de flux entrants (classification, option)

---

*Historique : [brief v1](docs/brief.md) (POC d'origine) · [brief v2](docs/brief-v2.md) (plateforme, source de vérité).*
