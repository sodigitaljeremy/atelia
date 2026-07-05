# Décisions d'architecture (ADR)

Les décisions structurantes sont consignées en ADR (un fichier par décision) dans
[`adr/`](adr/). Format : Titre · Statut · Date · Contexte · Décision · Conséquences.

| ADR | Décision | Statut |
|---|---|---|
| [ADR-101](adr/ADR-101-plateforme-modulaire.md) | Plateforme modulaire avec registre de modules (router + schema + méta nav) | Accepté / implémenté (R0) |
| [ADR-102](adr/ADR-102-anonymisation-pme-fictive.md) | Anonymisation : PME fictive paramétrable (`settings.company_name`), aucune entreprise réelle | Accepté / implémenté (R0) |
| [ADR-103](adr/ADR-103-rag-pgvector.md) | RAG sur pgvector (mono-base, souverain) | Accepté, non encore implémenté (M2) |
| [ADR-104](adr/ADR-104-agent-function-calling-api-publiques.md) | Agent M3 en function-calling sur API publiques officielles (pas de scraping) | Accepté, non encore implémenté (M3) |
| [ADR-105](adr/ADR-105-donnees-publiques-synthetiques.md) | Données publiques + synthétiques uniquement | Accepté — appliqué sur M1 ; volet public à venir (M2/M3) |
| [ADR-106](adr/ADR-106-couche-llm-agnostique.md) | Couche LLM agnostique : Mistral par défaut, swappable Claude via LiteLLM | Accepté / implémenté (Slice 0) |

Les ADR historiques du POC v1 (numérotés ADR-001…005 dans les commentaires du code)
sont antérieurs à cette série ; leurs décisions toujours en vigueur sont reprises
ci-dessus (ex. ADR-001 → ADR-106, ADR-004 → ADR-105).
