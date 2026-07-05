-- Schéma AtelIA — idempotent, exécuté à chaque démarrage (lifespan).

CREATE TABLE IF NOT EXISTS invoice (
    id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    source          TEXT        NOT NULL DEFAULT 'factur-x',
    profile         TEXT,
    supplier_name   TEXT,
    supplier_siren  TEXT,
    invoice_number  TEXT,
    issue_date      DATE,
    due_date        DATE,
    currency        TEXT        NOT NULL DEFAULT 'EUR',
    total_ht        NUMERIC(12, 2),
    total_vat       NUMERIC(12, 2),
    total_ttc       NUMERIC(12, 2),
    status          TEXT        NOT NULL DEFAULT 'en_validation'
                    CHECK (status IN ('en_validation', 'validee', 'rejetee')),
    confidence      REAL        NOT NULL DEFAULT 1.0,
    raw_xml         TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS invoice_line (
    id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    invoice_id      BIGINT NOT NULL REFERENCES invoice (id) ON DELETE CASCADE,
    line_number     INTEGER NOT NULL,
    description     TEXT,
    quantity        NUMERIC(12, 3),
    unit_price      NUMERIC(12, 4),
    line_amount_ht  NUMERIC(12, 2),
    vat_rate        NUMERIC(5, 2)
);

CREATE INDEX IF NOT EXISTS idx_invoice_status ON invoice (status);
CREATE INDEX IF NOT EXISTS idx_invoice_line_invoice ON invoice_line (invoice_id);

-- Slice 2 : contrôles calculés à l'ingestion (anomalies, conformité, doublon)
ALTER TABLE invoice ADD COLUMN IF NOT EXISTS anomalies    JSONB   NOT NULL DEFAULT '[]';
ALTER TABLE invoice ADD COLUMN IF NOT EXISTS compliance   JSONB   NOT NULL DEFAULT '[]';
ALTER TABLE invoice ADD COLUMN IF NOT EXISTS is_duplicate BOOLEAN NOT NULL DEFAULT false;

-- Slice 3 : journal des gains, APPEND-ONLY. Un événement par facture validée,
-- jamais supprimé : rejeter ensuite la facture ne retire PAS le gain déjà acté
-- (le temps de saisie a réellement été économisé au moment de la validation).
-- UNIQUE (invoice_id) + ON CONFLICT DO NOTHING = idempotence (pas de double gain).
CREATE TABLE IF NOT EXISTS gain_event (
    id                BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    invoice_id        BIGINT REFERENCES invoice (id) ON DELETE SET NULL,
    minutes_saved     INTEGER       NOT NULL,
    cost_avoided_eur  NUMERIC(12, 2) NOT NULL,
    created_at        TIMESTAMPTZ   NOT NULL DEFAULT now(),
    UNIQUE (invoice_id)
);
