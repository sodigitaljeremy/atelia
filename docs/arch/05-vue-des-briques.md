# Vue des briques

*Rédigée après la Slice R0 — décrit uniquement ce qui existe.*

## Niveau 1 : socle + modules

L'application est organisée en trois zones sous `app/` :

```
app/
  core/       # le socle, partagé par tous les modules
    config.py     # settings (env), dont company_name — la PME fictive (source unique)
    db.py         # pool asyncpg ; applique au démarrage le schema.sql de chaque module
    llm.py        # couche LLM agnostique (LiteLLM) : Mistral par défaut, swappable en config
    registry.py   # contrat de module + découverte des modules installés
    templates.py  # env Jinja partagé : layout commun, filtres, contexte global (branding, nav)
    main.py       # app factory : routes du socle (/, /about, /health, /llm/ping) + montage des modules
  modules/    # un package = un module métier autonome
    invoices/     # M1 — factures fournisseurs (extraction déterministe Factur-X)
      __init__.py     # expose MODULE (le contrat, voir ci-dessous)
      router.py       # routes UI (écrans opérateur) + API JSON du module
      extraction.py  repository.py  services.py   # logique métier
      schema.sql      # tables du module, idempotent
      templates/      # écrans du module (étendent base.html du socle)
  shared/
    templates/    # base.html (layout + nav), home.html (hub), about.html (démarche)
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
| `schema_path` | `schema.sql` idempotent, appliqué à chaque démarrage par `core.db` |

Au démarrage, `registry._discover()` parcourt `app/modules/` (`pkgutil.iter_modules`),
importe chaque package et collecte son `MODULE`. Conséquences :

- **ajouter un module = déposer un package** conforme au contrat — aucun autre fichier à toucher ;
- le **hub d'accueil** (`home.html`) génère ses tuiles depuis `registry.modules` ;
- la **navigation** (`base.html`) agrège les entrées `nav` de chaque module ;
- chaque module **possède ses tables** : son schéma est appliqué par le socle, sans migration centrale.

Module actuellement enregistré : `invoices` (M1 — extraction déterministe Factur-X,
validation humaine, métriques de gains).
