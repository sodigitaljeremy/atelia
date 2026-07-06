# AtelIA — l'atelier IA d'une PME (fictive)

**Plateforme de démonstration AI Engineering** : quatre problèmes métier réels d'une PME
agroalimentaire fictive (« Conservia »), résolus chacun avec la technique adaptée — et
jamais un LLM plaqué là où il n'apporte rien.

**Démo live : [atel-ia.fr](https://atel-ia.fr)** · [Roadmap](docs/brief-v2.md) ·
[Architecture (arc42 + ADR)](docs/arch/README.md)

<!-- 📸 CAPTURE 1 : le hub d'accueil (les 4 tuiles) -->

## Le problème démontré

Intégrer l'IA en entreprise, ce n'est pas brancher un chatbot : c'est diagnostiquer un
besoin et choisir l'approche qui le résout au juste coût — **déterministe** quand la donnée
est structurée, **RAG** pour le documentaire, **agent** pour l'orchestration,
**classification** pour le non-structuré — avec un humain dans la boucle dès qu'une
décision engage. C'est cette capacité de diagnostic que la plateforme prouve, sur pièce.

## Les 4 modules

| Module | Technique prouvée | Vraie donnée | Statut |
|---|---|---|---|
| 🧾 Factures | Extraction déterministe + human-in-the-loop | Factur-X synthétiques (EN 16931) | ✅ déployé |
| 📚 Conformité | RAG sourcé, citations obligatoires | Règlement INCO 1169/2011 (EUR-Lex officiel) | ✅ déployé |
| 🔎 Fournisseurs | Agent function-calling multi-API | API d'État live (RNE/Sirene, BODACC) | ✅ déployé |
| 📨 Triage | Classification LLM zero-shot encadrée | Messages synthétiques | ✅ déployé |

### 🧾 Factures fournisseurs — le déterminisme assumé

Le XML Factur-X embarqué fait foi : extraction **sans aucun LLM**, exacte à 100 %.
Contrôles automatiques (totaux, TVA, dates, doublons) avec sévérités, validation humaine
obligatoire (les cas bloquants exigent une confirmation explicite, vérifiée côté serveur),
gains mesurés dans un **journal append-only jamais recalculé** (auditabilité), export ERP
en JSON.

### 📚 Assistant conformité — le RAG qui sait dire « je ne sais pas »

Le texte officiel du règlement INCO (consolidé EUR-Lex) est chunké **par article**
(unité citable), vectorisé (mistral-embed) dans **pgvector**. Les réponses sont générées
uniquement depuis les passages retrouvés, **citent leurs articles**, et les sources
s'affichent pour vérification. Hors corpus, défense en deux couches : un seuil de
similarité coupe le hors-sujet **avant tout appel LLM**, et le grounding du prompt refuse
le reste — testé sur « quel est le taux de TVA ? » : réponse « je ne trouve pas », zéro invention.

### 🔎 Fiabilité fournisseurs — un vrai agent, un score qui ne ment pas

Le modèle **décide lui-même** d'appeler ses outils (function-calling, `tool_choice=auto`) :
il identifie l'entreprise via l'API Recherche d'entreprises, réutilise le SIREN pour
interroger le **BODACC** (procédures collectives), et son raisonnement s'affiche tour par
tour. Le score de fiabilité est **calculé en code** (barème fixe, entreprise cessée
éliminatoire) — le LLM le reçoit et le commente, il ne le produit jamais. Les alertes
BODACC viennent de la donnée brute de l'API, pas du texte du modèle.

<!-- 📸 CAPTURE 2 : la timeline de l'agent (2 tool_calls) + le score expliqué -->

### 📨 Triage des messages — le zero-shot sous contrainte

Classification de messages entrants (réclamations, demandes) en zero-shot : catégories et
priorités **fermées par le typage** (validation Pydantic, retry motivé si le JSON dévie).
Et parce qu'on ne confie pas le critique à un LLM : un **garde-fou déterministe** force la
priorité « critique » sur tout signal de sécurité alimentaire — même quand le message a
l'air anodin (« petite remarque : des traces de noisette non mentionnées… »).

<!-- 📸 CAPTURE 3 : le message « anodin » forcé en Sécurité/critique par le garde-fou -->

## Le fil rouge

- **Couche LLM agnostique** : tout appel passe par LiteLLM → Mistral (souverain) ;
  basculer vers Claude = une variable d'environnement.
- **Le LLM travaille, le code décide du critique** : score fournisseurs, garde-fou
  sécurité, seuil hors-corpus, alertes — tout ce qui engage est déterministe.
- **Human-in-the-loop** : aucune écriture sans validation d'un opérateur.
- **Données publiques ou synthétiques uniquement** — zéro donnée personnelle réelle (RGPD).
- **Prouvé et livré en continu** : 85 tests, chaque tranche déployée avant la suivante.

## Architecture

Un socle (`app/core/` : config, DB, couche LLM, registre) héberge des **modules
enfichables** (`app/modules/`) : un module = un package exposant son contrat (routes,
schéma SQL idempotent appliqué au démarrage, métadonnées, hook d'initialisation). Le hub
et la navigation se génèrent depuis le registre — ajouter un cas d'usage = déposer un
dossier. Détails : [arc42](docs/arch/README.md), décisions dans les
[ADR-101…107](docs/arch/09-decisions-architecture.md).

## Stack

Python 3.12 · FastAPI · PostgreSQL + **pgvector** · **LiteLLM** → Mistral (swappable) ·
Jinja2 + HTMX (zéro build front) · uv · Docker Compose · Coolify/Hetzner, auto-deploy sur
push `main` ([détails déploiement](docs/arch/07-vue-deploiement.md)).

## Lancement local

```bash
cp .env.example .env   # renseigner MISTRAL_API_KEY et POSTGRES_PASSWORD
docker compose up --build
```

- UI : http://localhost:8000 · API : http://localhost:8000/docs · santé : `/health`
- Tests et lint : `uv run pytest` · `uv run ruff check .`

## Note honnête

Conservia est une **PME fictive**. Les factures et messages sont synthétiques ; le corpus
réglementaire et les API d'entreprises sont réels et publics. AtelIA est un
**démonstrateur** de pratiques d'intégration IA — pas un produit en exploitation.
