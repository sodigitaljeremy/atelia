# ADR-101 — Plateforme modulaire avec registre de modules

**Statut** : Accepté / implémenté (Slice R0)
**Date** : 2026-07-05

## Contexte

AtelIA est né POC mono-cas (traitement de factures, app plate sous `app/`). La v2 en fait
une plateforme portfolio destinée à accueillir plusieurs cas d'usage (M1 factures, puis
M2 RAG, M3 agent, M4 triage), chacun démontrant une technique différente. Ajouter un cas
d'usage ne doit pas toucher au reste : la structure elle-même fait partie de la démonstration.

## Décision

Organiser le code en **socle + modules enfichables**, reliés par un registre
(`app/core/registry.py`) :

- un module = un package dans `app/modules/` exposant un objet `MODULE`, instance du
  contrat `Module` : `slug`, `titre`, `probleme` (une phrase), `technique`, `icone`,
  `router` (routes UI + API), `schema_path` (SQL idempotent), `nav` (liens de topbar) ;
- le registre **découvre** les modules à l'import (`pkgutil.iter_modules` sur
  `app/modules/`) et les trie par slug ;
- le socle consomme le registre : `core/db.py` applique le `schema.sql` de chaque module
  au démarrage, `core/main.py` (app factory) monte chaque `router`, le hub (`home.html`)
  génère ses tuiles et `base.html` sa navigation depuis `registry.modules` ;
- sens des dépendances : `modules/* → core` uniquement — jamais l'inverse, jamais de
  module à module.

## Conséquences

- Ajouter un module = déposer un package conforme au contrat ; aucun autre fichier à modifier.
- Chaque module possède ses tables (schéma appliqué par le socle) et ses templates
  (qui étendent `base.html` du socle via `core/templates.py`).
- **Compromis / limites** :
  - pas de migrations : les schémas sont idempotents (`CREATE … IF NOT EXISTS`), donc un
    `ALTER` de table existante devra être géré à la main le jour venu ;
  - la découverte importe tous les packages de `app/modules/` au démarrage — pas de
    mécanisme d'activation/désactivation d'un module ;
  - pas de gestion de dépendances entre modules (acceptable : elles sont interdites).
