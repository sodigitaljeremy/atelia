# Corpus réglementaire (module Conformité)

Un dossier par document : `meta.json` (titre, source_celex, source_date, source_url)
+ un ou plusieurs `.md` contenant le texte OFFICIEL (copié depuis EUR-Lex, jamais
reconstitué de mémoire), balisé par unité citable :

    ## Article 9 — Liste des mentions obligatoires
    [texte exact...]

    ## Annexe II — Substances ou produits provoquant des allergies ou intolérances
    [texte exact...]

L'ingestion (`scripts/ingest_compliance.py`, idempotente, aussi lancée au démarrage)
découpe sur les `## `, vectorise les chunks manquants et les indexe dans pgvector.
