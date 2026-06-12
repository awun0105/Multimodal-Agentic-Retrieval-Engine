-- Harness v0 schema - migration 003
-- Align durable state with existing-project onboarding workflows.

PRAGMA foreign_keys = OFF;

BEGIN;

CREATE TABLE intake_next (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at    TEXT    NOT NULL DEFAULT (datetime('now')),
    input_type    TEXT    NOT NULL
                         CHECK(input_type IN (
                           'new_spec','existing_project_onboarding',
                           'spec_slice','change_request','new_initiative',
                           'maintenance','harness_improvement'
                         )),
    summary       TEXT    NOT NULL,
    risk_lane     TEXT    NOT NULL
                         CHECK(risk_lane IN ('tiny','normal','high_risk')),
    risk_flags    TEXT,
    affected_docs TEXT,
    story_id      TEXT,
    notes         TEXT
);

INSERT INTO intake_next (
    id, created_at, input_type, summary, risk_lane, risk_flags,
    affected_docs, story_id, notes
)
SELECT
    id, created_at, input_type, summary, risk_lane, risk_flags,
    affected_docs, story_id, notes
FROM intake;

DROP TABLE intake;
ALTER TABLE intake_next RENAME TO intake;

CREATE TABLE story_next (
    id                    TEXT PRIMARY KEY,
    title                 TEXT NOT NULL,
    created_at            TEXT NOT NULL DEFAULT (datetime('now')),
    risk_lane             TEXT NOT NULL
                          CHECK(risk_lane IN ('tiny','normal','high_risk')),
    contract_doc          TEXT,
    status                TEXT NOT NULL DEFAULT 'planned'
                          CHECK(status IN (
                            'planned','in_progress','partial','unknown',
                            'not_implemented','implemented','changed','retired'
                          )),
    unit_proof            INTEGER NOT NULL DEFAULT 0,
    integration_proof     INTEGER NOT NULL DEFAULT 0,
    e2e_proof             INTEGER NOT NULL DEFAULT 0,
    platform_proof        INTEGER NOT NULL DEFAULT 0,
    evidence              TEXT,
    notes                 TEXT,
    verify_command        TEXT,
    last_verified_at      TEXT,
    last_verified_result  TEXT
                          CHECK(last_verified_result IN ('pass','fail') OR
                                last_verified_result IS NULL)
);

INSERT INTO story_next (
    id, title, created_at, risk_lane, contract_doc, status, unit_proof,
    integration_proof, e2e_proof, platform_proof, evidence, notes,
    verify_command, last_verified_at, last_verified_result
)
SELECT
    id, title, created_at, risk_lane, contract_doc, status, unit_proof,
    integration_proof, e2e_proof, platform_proof, evidence, notes,
    verify_command, last_verified_at, last_verified_result
FROM story;

DROP TABLE story;
ALTER TABLE story_next RENAME TO story;

INSERT INTO schema_version (version) VALUES (3);

COMMIT;

PRAGMA foreign_keys = ON;
