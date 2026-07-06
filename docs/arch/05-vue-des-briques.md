# Vue des briques

*Mise à jour après M4 — décrit uniquement ce qui existe.*

## Niveau 1 : socle + modules

L'application est organisée en trois zones sous `app/` :

```
app/
  core/       # le socle, partagé par tous les modules
    config.py     # settings (env) : company_name (PME fictive), hypothèses de gains,
                  # URLs d'API, demo_mode, modèles LLM
    db.py         # pool asyncpg ; applique au démarrage le schema.sql de chaque module
    llm.py        # couche LLM agnostique (LiteLLM) : complete, complete_messages
                  # (tool-use format OpenAI), embed, embed_many — Mistral par défaut
    registry.py   # contrat de module + découverte, tri par ordre narratif
    templates.py  # env Jinja partagé : layout, filtres (eur, qty, extrait), contexte global
    main.py       # app factory : routes du socle (/, /about, /health, /llm/ping),
                  # montage des modules, hooks on_startup
  modules/    # un package = un module métier autonome
    invoices/     # M1 — extraction déterministe Factur-X, contrôles, gains append-only
      router.py  extraction.py  checks.py  repository.py  services.py  gains.py
      schema.sql  templates/
    compliance/   # M2 — RAG sourcé sur le règlement INCO officiel
      router.py  ingestion.py  repository.py  rag.py
      schema.sql  templates/
    suppliers/    # M3 — agent function-calling sur API publiques (sans table)
      router.py  client.py  bodacc.py  agent.py
      templates/
    triage/       # M4 — classification zero-shot encadrée (sans table)
      router.py  classifier.py
      templates/
  shared/
    templates/    # base.html (layout + nav + composants communs), home.html (hub), about.html
```

Dépendances autorisées : `modules/* → core` et `modules/* → shared/templates`
(via `core.templates`). Jamais l'inverse, jamais de module à module.

## Le pattern de registre (`core/registry.py`)

Un module est un package de `app/modules/` exposant un objet `MODULE`, instance du
contrat `Module` :

| Champ | Rôle |
|---|---|
| `slug`, `titre`, `probleme`, `technique`, `icone` | métadonnées : tuile du hub et navigation |
| `nav` | liens du module dans la barre de navigation `(libellé, url, clé active)` |
| `router` | toutes les routes du module (UI + API), monté par l'app factory |
| `schema_path` | `schema.sql` idempotent appliqué au démarrage — `None` si le module n'a pas de table |
| `on_startup` | hook optionnel post-schéma (backfill des gains M1, ingestion du corpus M2 par empreinte) |
| `ordre` | position dans le hub et la nav (ordre narratif : déterministe → RAG → agent → NLP) |

Au démarrage, le registre parcourt `app/modules/` (`pkgutil.iter_modules`), importe chaque
package et collecte son `MODULE` (découverte paresseuse — PEP 562). Conséquences :

- **ajouter un module = déposer un package** conforme au contrat — aucun autre fichier à toucher ;
- le **hub d'accueil** (`home.html`) génère ses tuiles depuis `registry.modules` ;
- la **navigation** (`base.html`) agrège les entrées `nav` de chaque module ;
- chaque module **possède ses tables** (quand il en a) : schéma appliqué par le socle,
  migrations de données via son hook `on_startup` (idempotentes par contrainte ou empreinte).

Modules enregistrés : `invoices` (M1), `compliance` (M2), `suppliers` (M3), `triage` (M4) —
le pattern a été éprouvé quatre fois, dont deux modules sans table.
