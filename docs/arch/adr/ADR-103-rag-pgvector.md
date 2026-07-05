# ADR-103 — RAG sur pgvector (mono-base, souverain)

**Statut** : Accepté, non encore implémenté (prévu Slice M2)
**Date** : 2026-07-05

## Contexte

Le module M2 (assistant conformité & qualité) fera de la recherche documentaire sur un
corpus réglementaire public : il lui faut un stockage de vecteurs d'embeddings. L'infra
existante comprend déjà PostgreSQL avec l'extension **pgvector** (image
`pgvector/pgvector:pg16`, `CREATE EXTENSION IF NOT EXISTS vector` à chaque démarrage dans
`app/core/db.py`, extension vérifiée par `/health`). L'alternative serait une base
vectorielle dédiée (Qdrant, Weaviate, service managé…).

## Décision

Faire le RAG de M2 sur **pgvector**, dans la base PostgreSQL existante :

- **mono-base** : embeddings et données métier au même endroit, un seul service à
  opérer, sauvegarder et surveiller ;
- **souverain** : self-hosté avec le reste de la stack, aucune donnée envoyée à un
  service vectoriel tiers ;
- les embeddings seront produits par `mistral-embed` via la couche LLM du socle
  (`app/core/llm.py`, fonction `embed` — déjà en place et testée par `/llm/ping`) ;
- le schéma vectoriel appartiendra au module M2 (`schema.sql` idempotent, pattern ADR-101).

## Conséquences

- Zéro service supplémentaire ; le module M2 s'ajoutera par le mécanisme standard du registre.
- **Compromis / limites** :
  - pgvector est moins riche qu'une base vectorielle dédiée (tuning d'index, filtrage
    hybride avancé, scaling horizontal) — acceptable pour un corpus petit et net, qui est
    le périmètre affiché de M2 ;
  - à ce jour **rien du RAG n'existe** (ni table d'embeddings, ni chunking, ni retrieval) :
    seule l'extension est installée et vérifiée. Cet ADR fige le choix d'infra, pas une
    implémentation.
