-- ============================================================
-- Solvra Kernel — Supabase Schema
-- ============================================================
-- Run this in your Supabase SQL editor before first use.
-- All tables follow the kernel's data model exactly.
--
-- Key design rules:
--   - measurements: IMMUTABLE — no updates, corrections are new rows
--   - audit_events:  APPEND-ONLY — no updates or deletes ever
--   - All tables have row-level security enabled (RLS)
--   - user_id is always a text column matching Supabase auth.uid()
-- ============================================================

-- ── MEASUREMENTS ────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS measurements (
    id              TEXT PRIMARY KEY,
    user_id         TEXT NOT NULL,
    signal_id       TEXT NOT NULL,
    value           FLOAT NOT NULL,
    unit            TEXT NOT NULL,
    timestamp       TIMESTAMPTZ NOT NULL,
    source_type     TEXT NOT NULL DEFAULT 'manual_entry',
    entry_method    TEXT NOT NULL DEFAULT 'web_form',
    quality_flags   TEXT[] DEFAULT '{}',
    notes           TEXT,
    supersedes_id   TEXT,
    is_deleted      BOOLEAN NOT NULL DEFAULT FALSE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Immutability enforced: no UPDATE allowed on measurements
-- Corrections create new rows with supersedes_id set

CREATE INDEX IF NOT EXISTS idx_measurements_user_signal
    ON measurements (user_id, signal_id, timestamp DESC);

-- ── AUDIT EVENTS ────────────────────────────────────────────
-- Append-only. Never updated or deleted.
CREATE TABLE IF NOT EXISTS audit_events (
    id              TEXT PRIMARY KEY,
    event_type      TEXT NOT NULL,
    actor           TEXT NOT NULL,
    entity_id       TEXT NOT NULL,
    entity_type     TEXT NOT NULL,
    reason_code     TEXT,
    details         TEXT,
    previous_hash   TEXT,
    hash            TEXT,
    timestamp       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_audit_events_entity
    ON audit_events (entity_id, timestamp DESC);

-- ── BASELINES ───────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS baselines (
    id                  TEXT PRIMARY KEY,
    user_id             TEXT NOT NULL,
    signal_id           TEXT NOT NULL,
    feature_type        TEXT NOT NULL,  -- 'baseline_short' or 'baseline_long'
    value               FLOAT NOT NULL,
    window_start        TIMESTAMPTZ NOT NULL,
    window_end          TIMESTAMPTZ NOT NULL,
    measurement_count   INT NOT NULL,
    method              TEXT NOT NULL,
    quality_weight_sum  FLOAT NOT NULL,
    uncertainty         TEXT NOT NULL,
    version             INT NOT NULL DEFAULT 1,
    computed_at         TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_baselines_user_signal
    ON baselines (user_id, signal_id, computed_at DESC);

-- ── FINDINGS ────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS findings (
    id                          TEXT PRIMARY KEY,
    user_id                     TEXT NOT NULL,
    signal_id                   TEXT NOT NULL,
    finding_type                TEXT NOT NULL,
    description                 TEXT NOT NULL,
    evidence_window_start       TIMESTAMPTZ NOT NULL,
    evidence_window_end         TIMESTAMPTZ NOT NULL,
    confidence                  FLOAT NOT NULL,
    uncertainty                 TEXT NOT NULL,
    supporting_measurement_ids  TEXT[] DEFAULT '{}',
    baseline_ref_id             TEXT,
    detected_at                 TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_findings_user
    ON findings (user_id, detected_at DESC);

-- ── ALERTS ──────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS alerts (
    id                  TEXT PRIMARY KEY,
    user_id             TEXT NOT NULL,
    severity            TEXT NOT NULL,
    title               TEXT NOT NULL,
    message             TEXT NOT NULL,
    safe_next_step      TEXT NOT NULL,
    uncertainty         TEXT NOT NULL,
    escalation_level    TEXT,
    acknowledged        BOOLEAN NOT NULL DEFAULT FALSE,
    acknowledged_at     TIMESTAMPTZ,
    suppressible        BOOLEAN NOT NULL DEFAULT TRUE,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_alerts_user
    ON alerts (user_id, created_at DESC);

-- ── BASELINE CONTEXT NOTES ──────────────────────────────────
CREATE TABLE IF NOT EXISTS baseline_context_notes (
    id                          TEXT PRIMARY KEY,
    user_id                     TEXT NOT NULL,
    signal_id                   TEXT NOT NULL,
    signal_name                 TEXT NOT NULL,
    personal_baseline           FLOAT NOT NULL,
    personal_baseline_unit      TEXT NOT NULL,
    population_normal_low       FLOAT NOT NULL,
    population_normal_high      FLOAT NOT NULL,
    status                      TEXT NOT NULL,
    context_message             TEXT NOT NULL,
    guideline_source            TEXT NOT NULL,
    debate_note                 TEXT,
    acknowledged                BOOLEAN NOT NULL DEFAULT FALSE,
    acknowledged_at             TIMESTAMPTZ,
    dormant                     BOOLEAN NOT NULL DEFAULT FALSE,
    created_at                  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_context_notes_user
    ON baseline_context_notes (user_id, signal_id);

-- ── ROW LEVEL SECURITY ──────────────────────────────────────
-- Users can only see their own data.
-- Enable RLS on all tables.

ALTER TABLE measurements           ENABLE ROW LEVEL SECURITY;
ALTER TABLE audit_events           ENABLE ROW LEVEL SECURITY;
ALTER TABLE baselines              ENABLE ROW LEVEL SECURITY;
ALTER TABLE findings               ENABLE ROW LEVEL SECURITY;
ALTER TABLE alerts                 ENABLE ROW LEVEL SECURITY;
ALTER TABLE baseline_context_notes ENABLE ROW LEVEL SECURITY;

-- Policies: authenticated users see only their own rows
CREATE POLICY "Users see own measurements"
    ON measurements FOR ALL
    USING (auth.uid()::text = user_id);

CREATE POLICY "Users see own baselines"
    ON baselines FOR ALL
    USING (auth.uid()::text = user_id);

CREATE POLICY "Users see own findings"
    ON findings FOR ALL
    USING (auth.uid()::text = user_id);

CREATE POLICY "Users see own alerts"
    ON alerts FOR ALL
    USING (auth.uid()::text = user_id);

CREATE POLICY "Users see own context notes"
    ON baseline_context_notes FOR ALL
    USING (auth.uid()::text = user_id);

-- Audit events: system writes, users can read their own
CREATE POLICY "Users see own audit events"
    ON audit_events FOR SELECT
    USING (
        entity_id IN (
            SELECT id FROM measurements WHERE user_id = auth.uid()::text
        )
    );

-- ============================================================
-- Schema complete. Run python solvra_kernel/tests/test_kernel.py
-- to verify kernel integrity before connecting.
-- ============================================================
