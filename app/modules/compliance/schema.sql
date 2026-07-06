-- Module Conformité (M2) — corpus réglementaire indexé pour le RAG. Idempotent.
-- Tables préfixées : chaque module possède ses tables (ADR-101), et « document »/
-- « chunk » nus seraient trop génériques pour une base partagée entre modules.

CREATE TABLE IF NOT EXISTS compliance_document (
    id           BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    titre        TEXT        NOT NULL,
    source_celex TEXT        NOT NULL UNIQUE,
    source_date  DATE,
    source_url   TEXT,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Un chunk = une unité juridiquement CITABLE (article, annexe, ou paragraphe précis),
-- jamais un découpage aveugle à N caractères. UNIQUE(document_id, ref_article) est la
-- clé de l'idempotence de l'ingestion (relançable sans doublon).
CREATE TABLE IF NOT EXISTS compliance_chunk (
    id           BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    document_id  BIGINT NOT NULL REFERENCES compliance_document (id) ON DELETE CASCADE,
    ref_article  TEXT   NOT NULL,
    contenu      TEXT   NOT NULL,
    embedding    vector(1024) NOT NULL,
    UNIQUE (document_id, ref_article)
);

-- Pas d'index ANN (ivfflat/hnsw) : corpus de quelques dizaines de chunks, la recherche
-- exacte est à la fois plus juste et plus simple. À revoir si le corpus grossit vraiment.

-- Lot 2 : détection de changement du corpus. Le hash du contenu chunké permet à
-- l'ingestion de régénérer les embeddings quand le pipeline de nettoyage évolue
-- (hash différent → chunks supprimés et ré-indexés), tout en restant no-op sinon.
ALTER TABLE compliance_document ADD COLUMN IF NOT EXISTS corpus_hash TEXT;
