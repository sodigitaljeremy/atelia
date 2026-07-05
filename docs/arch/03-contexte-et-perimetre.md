# Contexte et périmètre

## Acteurs et systèmes voisins

| Acteur / système | Interaction | État |
|---|---|---|
| **Visiteur / opérateur** | UI web (Jinja2 + HTMX) : hub, dépôt de facture, écran de contrôle/validation, dashboard de gains | En place |
| **ERP** (simulé) | API JSON : `POST /api/invoices` (ingestion PDF), `GET /api/invoices?status=validee` (export du validé) — aucune intégration ERP réelle, le point d'entrée est démontré | En place |
| **Fournisseur LLM** (Mistral, swappable) | Via la couche `core/llm.py` uniquement (`/llm/ping` pour la preuve de chaîne) | En place |
| Corpus réglementaire public (INCO, facturation électronique, HACCP) | Ingestion RAG | *À venir (M2)* |
| API publiques (Recherche d'entreprises/Sirene, BODACC, Open Food Facts) | Appels live orchestrés par agent | *À venir (M3)* |

## Frontières — ce que la plateforme n'est PAS

- **Pas de donnée privée réelle** : factures synthétiques (générées par `scripts/`), PME et
  fournisseurs fictifs ; les futures données réelles seront exclusivement publiques (ADR-105).
- **Pas une Plateforme Agréée (PA/PDP)** ni un outil de transmission fiscale : le module Factures
  démontre l'extraction et le contrôle, pas la conformité réglementaire d'un opérateur de
  facturation électronique. La checklist « mentions attendues » est factuelle et porte son
  disclaimer : ce n'est pas un avis juridique.
- **Pas d'écriture comptable réelle** : « valider et comptabiliser » s'arrête à la base de la
  plateforme ; l'ERP est représenté par l'API JSON.
- **Pas d'authentification** à ce stade : démo publique, données réinitialisables
  (`demo_mode`, ADR-107).
