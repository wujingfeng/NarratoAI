-- Generated from Alembic PostgreSQL migration chain through 0027_video_translation_voice_replacement_charge.
BEGIN;

CREATE TABLE alembic_version (
    version_num VARCHAR(32) NOT NULL, 
    CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num)
);

-- Running upgrade  -> 0001_business_base

INSERT INTO alembic_version (version_num) VALUES ('0001_business_base') RETURNING alembic_version.version_num;

-- Running upgrade 0001_business_base -> 0002_users

CREATE TABLE users (
    id VARCHAR(64) NOT NULL, 
    email VARCHAR(320) NOT NULL, 
    password_hash VARCHAR(512) NOT NULL, 
    status VARCHAR(16) NOT NULL, 
    password_version INTEGER NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    CONSTRAINT ck_users_status CHECK (status IN ('active', 'disabled')), 
    CONSTRAINT ck_users_email_normalized CHECK (email = lower(email) AND email = trim(email))
);

CREATE UNIQUE INDEX ix_users_email ON users (email);

UPDATE alembic_version SET version_num='0002_users' WHERE alembic_version.version_num = '0001_business_base';

-- Running upgrade 0002_users -> 0003_billing

CREATE TABLE credit_accounts (
    user_id VARCHAR(64) NOT NULL, 
    balance INTEGER NOT NULL, 
    version INTEGER NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (user_id), 
    CONSTRAINT ck_credit_accounts_balance CHECK (balance >= 0), 
    FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE RESTRICT
);

CREATE TABLE credit_ledger (
    id SERIAL NOT NULL, 
    user_id VARCHAR(64) NOT NULL, 
    entry_type VARCHAR(32) NOT NULL, 
    amount INTEGER NOT NULL, 
    idempotency_key VARCHAR(256) NOT NULL, 
    reference_id VARCHAR(64), 
    reason VARCHAR(128) NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    CONSTRAINT ck_credit_ledger_nonzero_amount CHECK (amount <> 0), 
    CONSTRAINT ck_credit_ledger_entry_type CHECK (entry_type IN ('signup_bonus', 'operator_grant', 'charge', 'refund')), 
    FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE RESTRICT, 
    CONSTRAINT uq_credit_ledger_idempotency UNIQUE (user_id, idempotency_key)
);

CREATE INDEX ix_credit_ledger_reference ON credit_ledger (reference_id);

CREATE TABLE product_prices (
    id SERIAL NOT NULL, 
    product VARCHAR(64) NOT NULL, 
    version INTEGER NOT NULL, 
    credits_per_minute INTEGER NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    CONSTRAINT ck_product_prices_version CHECK (version > 0), 
    CONSTRAINT ck_product_prices_credits_per_minute CHECK (credits_per_minute > 0), 
    CONSTRAINT uq_product_prices_product_version UNIQUE (product, version)
);

UPDATE alembic_version SET version_num='0003_billing' WHERE alembic_version.version_num = '0002_users';

-- Running upgrade 0003_billing -> 0004_projects_assets

CREATE TABLE projects (
    id VARCHAR(64) NOT NULL, 
    user_id VARCHAR(64) NOT NULL, 
    product VARCHAR(64) NOT NULL, 
    status VARCHAR(32) NOT NULL, 
    is_locked BOOLEAN NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    CONSTRAINT ck_projects_status CHECK (status IN ('draft', 'uploading', 'validating', 'ready', 'queued', 'analyzing', 'waiting_for_edit', 'render_queued', 'rendering', 'completed', 'failed', 'deleting', 'deleted')), 
    FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE RESTRICT
);

CREATE INDEX ix_projects_user_created ON projects (user_id, created_at);

CREATE TABLE assets (
    id VARCHAR(64) NOT NULL, 
    user_id VARCHAR(64) NOT NULL, 
    project_id VARCHAR(64) NOT NULL, 
    asset_type VARCHAR(16) NOT NULL, 
    status VARCHAR(16) NOT NULL, 
    filename VARCHAR(255) NOT NULL, 
    bucket VARCHAR(255) NOT NULL, 
    object_key VARCHAR(1024) NOT NULL, 
    cdn_url VARCHAR(2048) NOT NULL, 
    size_bytes BIGINT NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    CONSTRAINT ck_assets_type CHECK (asset_type IN ('video', 'subtitle')), 
    CONSTRAINT ck_assets_status CHECK (status IN ('validating', 'ready', 'invalid')), 
    CONSTRAINT ck_assets_filename_length CHECK (length(filename) BETWEEN 1 AND 255), 
    CONSTRAINT ck_assets_size_bytes CHECK (size_bytes >= 0), 
    FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE RESTRICT, 
    FOREIGN KEY(project_id) REFERENCES projects (id) ON DELETE RESTRICT, 
    CONSTRAINT uq_assets_bucket_object_key UNIQUE (bucket, object_key)
);

CREATE INDEX ix_assets_project_type ON assets (project_id, asset_type);

CREATE INDEX ix_assets_user_created ON assets (user_id, created_at);

UPDATE alembic_version SET version_num='0004_projects_assets' WHERE alembic_version.version_num = '0003_billing';

-- Running upgrade 0004_projects_assets -> 0005_asset_probe_reservations

ALTER TABLE assets ADD COLUMN core_task_id VARCHAR(128);

ALTER TABLE assets ADD COLUMN reservation_expires_at TIMESTAMP WITH TIME ZONE;

UPDATE alembic_version SET version_num='0005_asset_probe_reservations' WHERE alembic_version.version_num = '0004_projects_assets';

-- Running upgrade 0005_asset_probe_reservations -> 0006_workflows

CREATE TABLE workflow_template_snapshots (
    id VARCHAR(64) NOT NULL, 
    template_name VARCHAR(128) NOT NULL, 
    version VARCHAR(64) NOT NULL, 
    definition JSON NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    CONSTRAINT uq_workflow_templates_name_version UNIQUE (template_name, version)
);

CREATE TABLE workflows (
    id VARCHAR(64) NOT NULL, 
    user_id VARCHAR(64) NOT NULL, 
    project_id VARCHAR(64) NOT NULL, 
    template_snapshot_id VARCHAR(64) NOT NULL, 
    state VARCHAR(32) NOT NULL, 
    state_version INTEGER NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    CONSTRAINT ck_workflows_state CHECK (state IN ('draft', 'queued', 'running', 'waiting_for_edit', 'render_queued', 'completed', 'failed')), 
    CONSTRAINT ck_workflows_state_version CHECK (state_version >= 0), 
    FOREIGN KEY(project_id) REFERENCES projects (id) ON DELETE RESTRICT, 
    FOREIGN KEY(template_snapshot_id) REFERENCES workflow_template_snapshots (id) ON DELETE RESTRICT, 
    FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE RESTRICT, 
    CONSTRAINT uq_workflows_project_id UNIQUE (project_id)
);

CREATE INDEX ix_workflows_user_created ON workflows (user_id, created_at);

CREATE TABLE workflow_nodes (
    id VARCHAR(64) NOT NULL, 
    workflow_id VARCHAR(64) NOT NULL, 
    name VARCHAR(128) NOT NULL, 
    state VARCHAR(32) NOT NULL, 
    depends_on JSON NOT NULL, 
    retryable BOOLEAN NOT NULL, 
    manual_gate BOOLEAN NOT NULL, 
    max_attempts INTEGER NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    CONSTRAINT ck_workflow_nodes_state CHECK (state IN ('queued', 'running', 'waiting_for_edit', 'completed', 'failed')), 
    CONSTRAINT ck_workflow_nodes_max_attempts CHECK (max_attempts >= 1), 
    FOREIGN KEY(workflow_id) REFERENCES workflows (id) ON DELETE RESTRICT, 
    CONSTRAINT uq_workflow_nodes_workflow_name UNIQUE (workflow_id, name)
);

CREATE INDEX ix_workflow_nodes_workflow_state ON workflow_nodes (workflow_id, state);

CREATE TABLE workflow_node_attempts (
    id VARCHAR(64) NOT NULL, 
    workflow_node_id VARCHAR(64) NOT NULL, 
    attempt_number INTEGER NOT NULL, 
    state VARCHAR(32) NOT NULL, 
    core_task_id VARCHAR(128), 
    result JSON, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    completed_at TIMESTAMP WITH TIME ZONE, 
    PRIMARY KEY (id), 
    CONSTRAINT ck_workflow_node_attempts_state CHECK (state IN ('queued', 'running', 'completed', 'failed')), 
    CONSTRAINT ck_workflow_node_attempts_number CHECK (attempt_number >= 1), 
    FOREIGN KEY(workflow_node_id) REFERENCES workflow_nodes (id) ON DELETE RESTRICT, 
    CONSTRAINT uq_workflow_node_attempts_core_task_id UNIQUE (core_task_id), 
    CONSTRAINT uq_workflow_node_attempts_node_number UNIQUE (workflow_node_id, attempt_number)
);

CREATE INDEX ix_workflow_node_attempts_node_state ON workflow_node_attempts (workflow_node_id, state);

CREATE TABLE workflow_outbox (
    id VARCHAR(64) NOT NULL, 
    workflow_id VARCHAR(64) NOT NULL, 
    workflow_node_id VARCHAR(64), 
    event_type VARCHAR(128) NOT NULL, 
    idempotency_key VARCHAR(255) NOT NULL, 
    payload JSON NOT NULL, 
    status VARCHAR(16) NOT NULL, 
    attempt_count INTEGER NOT NULL, 
    available_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    sent_at TIMESTAMP WITH TIME ZONE, 
    PRIMARY KEY (id), 
    CONSTRAINT ck_workflow_outbox_status CHECK (status IN ('pending', 'sending', 'sent', 'dead')), 
    FOREIGN KEY(workflow_id) REFERENCES workflows (id) ON DELETE RESTRICT, 
    FOREIGN KEY(workflow_node_id) REFERENCES workflow_nodes (id) ON DELETE RESTRICT, 
    CONSTRAINT uq_workflow_outbox_idempotency_key UNIQUE (idempotency_key)
);

CREATE INDEX ix_workflow_outbox_status_created ON workflow_outbox (status, created_at);

UPDATE alembic_version SET version_num='0006_workflows' WHERE alembic_version.version_num = '0005_asset_probe_reservations';

-- Running upgrade 0006_workflows -> 0007_workflow_reconciliation

ALTER TABLE workflow_node_attempts ADD COLUMN state_version INTEGER DEFAULT '0' NOT NULL;

ALTER TABLE workflow_node_attempts ADD CONSTRAINT ck_workflow_node_attempts_state_version CHECK (state_version >= 0);

CREATE TABLE workflow_reconciliation_events (
    id VARCHAR(64) NOT NULL, 
    workflow_node_attempt_id VARCHAR(64) NOT NULL, 
    event_id VARCHAR(128) NOT NULL, 
    state_version INTEGER NOT NULL, 
    source VARCHAR(16) NOT NULL, 
    state VARCHAR(16) NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    CONSTRAINT ck_workflow_reconciliation_events_state_version CHECK (state_version >= 0), 
    FOREIGN KEY(workflow_node_attempt_id) REFERENCES workflow_node_attempts (id) ON DELETE RESTRICT, 
    CONSTRAINT uq_workflow_reconciliation_events_attempt_event UNIQUE (workflow_node_attempt_id, event_id), 
    CONSTRAINT uq_workflow_reconciliation_events_attempt_state_version UNIQUE (workflow_node_attempt_id, state_version)
);

UPDATE alembic_version SET version_num='0007_workflow_reconciliation' WHERE alembic_version.version_num = '0006_workflows';

-- Running upgrade 0007_workflow_reconciliation -> 0008_editor_revisions

CREATE TABLE editor_revisions (
    id VARCHAR(64) NOT NULL, 
    project_id VARCHAR(64) NOT NULL, 
    content JSON NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(project_id) REFERENCES projects (id) ON DELETE RESTRICT
);

UPDATE alembic_version SET version_num='0008_editor_revisions' WHERE alembic_version.version_num = '0007_workflow_reconciliation';

-- Running upgrade 0008_editor_revisions -> 0009_editor_drafts

CREATE TABLE editor_drafts (
    project_id VARCHAR(64) NOT NULL, 
    id VARCHAR(64) NOT NULL, 
    content JSON NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (project_id), 
    FOREIGN KEY(project_id) REFERENCES projects (id) ON DELETE RESTRICT, 
    UNIQUE (id)
);

UPDATE alembic_version SET version_num='0009_editor_drafts' WHERE alembic_version.version_num = '0008_editor_revisions';

-- Running upgrade 0009_editor_drafts -> 0010_registered_artifacts

CREATE TABLE artifacts (
    id VARCHAR(64) NOT NULL, 
    project_id VARCHAR(64) NOT NULL, 
    kind VARCHAR(64) NOT NULL, 
    cdn_url VARCHAR(2048) NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(project_id) REFERENCES projects (id) ON DELETE RESTRICT
);

CREATE INDEX ix_artifacts_project_created ON artifacts (project_id, created_at);

UPDATE alembic_version SET version_num='0010_registered_artifacts' WHERE alembic_version.version_num = '0009_editor_drafts';

-- Running upgrade 0010_registered_artifacts -> 0011_project_deletion_jobs

CREATE TABLE deletion_jobs (
    id VARCHAR(64) NOT NULL, 
    project_id VARCHAR(64) NOT NULL, 
    user_id VARCHAR(64) NOT NULL, 
    status VARCHAR(16) NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    CONSTRAINT ck_deletion_jobs_status CHECK (status IN ('pending')), 
    FOREIGN KEY(project_id) REFERENCES projects (id) ON DELETE RESTRICT, 
    FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE RESTRICT, 
    CONSTRAINT uq_deletion_jobs_project_id UNIQUE (project_id)
);

CREATE INDEX ix_deletion_jobs_user_created ON deletion_jobs (user_id, created_at);

UPDATE alembic_version SET version_num='0011_project_deletion_jobs' WHERE alembic_version.version_num = '0010_registered_artifacts';

-- Running upgrade 0011_project_deletion_jobs -> 0012_artifact_core_manifest_metadata

ALTER TABLE artifacts ADD COLUMN size BIGINT;

ALTER TABLE artifacts ADD COLUMN checksum VARCHAR(72);

ALTER TABLE artifacts ADD COLUMN content_type VARCHAR(255);

ALTER TABLE artifacts ADD COLUMN width INTEGER;

ALTER TABLE artifacts ADD COLUMN height INTEGER;

ALTER TABLE artifacts ADD COLUMN duration FLOAT;

UPDATE alembic_version SET version_num='0012_artifact_core_manifest_metadata' WHERE alembic_version.version_num = '0011_project_deletion_jobs';

-- Running upgrade 0012_artifact_core_manifest_metadata -> 0013_project_deletion_worker

ALTER TABLE deletion_jobs DROP CONSTRAINT ck_deletion_jobs_status;

ALTER TABLE deletion_jobs ADD COLUMN attempt_count INTEGER DEFAULT '0' NOT NULL;

ALTER TABLE deletion_jobs ADD COLUMN last_error VARCHAR(128);

ALTER TABLE deletion_jobs ADD CONSTRAINT ck_deletion_jobs_status CHECK (status IN ('pending', 'retryable_failed', 'completed'));

UPDATE alembic_version SET version_num='0013_project_deletion_worker' WHERE alembic_version.version_num = '0012_artifact_core_manifest_metadata';

-- Running upgrade 0013_project_deletion_worker -> 0014_asset_duration

ALTER TABLE assets ADD COLUMN duration_seconds FLOAT;

UPDATE alembic_version SET version_num='0014_asset_duration' WHERE alembic_version.version_num = '0013_project_deletion_worker';

-- Running upgrade 0014_asset_duration -> 0015_background_music

ALTER TABLE assets DROP CONSTRAINT ck_assets_type;

ALTER TABLE assets ADD CONSTRAINT ck_assets_type CHECK (asset_type IN ('video', 'subtitle', 'audio'));

CREATE TABLE project_background_music (
    project_id VARCHAR(64) NOT NULL, 
    asset_id VARCHAR(64) NOT NULL, 
    volume INTEGER DEFAULT '50' NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (project_id), 
    CONSTRAINT ck_project_bgm_volume CHECK (volume BETWEEN 0 AND 100), 
    FOREIGN KEY(asset_id) REFERENCES assets (id) ON DELETE RESTRICT, 
    FOREIGN KEY(project_id) REFERENCES projects (id) ON DELETE RESTRICT
);

UPDATE alembic_version SET version_num='0015_background_music' WHERE alembic_version.version_num = '0014_asset_duration';

-- Running upgrade 0015_background_music -> 0016_project_stages

ALTER TABLE projects ADD COLUMN current_stage VARCHAR(16) DEFAULT 'created' NOT NULL;

ALTER TABLE projects ADD CONSTRAINT ck_projects_current_stage CHECK (current_stage IN ('created', 'settings', 'analysis', 'edit', 'generate', 'export'));

UPDATE projects SET current_stage = CASE WHEN status IN ('waiting_for_edit') THEN 'edit' WHEN status IN ('render_queued', 'rendering') THEN 'generate' WHEN status IN ('completed') THEN 'export' WHEN status IN ('queued', 'analyzing') THEN 'analysis' WHEN status IN ('ready', 'uploading', 'validating') THEN 'settings' ELSE 'created' END;

CREATE TABLE project_narration_settings (
    project_id VARCHAR(64) NOT NULL, 
    settings JSON NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (project_id), 
    FOREIGN KEY(project_id) REFERENCES projects (id) ON DELETE RESTRICT
);

CREATE TABLE project_stage_history (
    id VARCHAR(64) NOT NULL, 
    project_id VARCHAR(64) NOT NULL, 
    from_stage VARCHAR(16), 
    to_stage VARCHAR(16) NOT NULL, 
    settings_snapshot JSON, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(project_id) REFERENCES projects (id) ON DELETE RESTRICT, 
    CONSTRAINT uq_project_stage_history_stage UNIQUE (project_id, to_stage)
);

CREATE INDEX ix_project_stage_history_project_created ON project_stage_history (project_id, created_at);

UPDATE alembic_version SET version_num='0016_project_stages' WHERE alembic_version.version_num = '0015_background_music';

-- Running upgrade 0016_project_stages -> 0017_workflow_cancellation

ALTER TABLE projects DROP CONSTRAINT ck_projects_status;

ALTER TABLE projects ADD CONSTRAINT ck_projects_status CHECK (status IN ('draft', 'uploading', 'validating', 'ready', 'queued', 'analyzing', 'waiting_for_edit', 'render_queued', 'rendering', 'completed', 'failed', 'cancelled', 'deleting', 'deleted'));

ALTER TABLE workflows DROP CONSTRAINT ck_workflows_state;

ALTER TABLE workflows ADD CONSTRAINT ck_workflows_state CHECK (state IN ('draft', 'queued', 'running', 'waiting_for_edit', 'render_queued', 'completed', 'failed', 'cancelled'));

ALTER TABLE workflow_nodes DROP CONSTRAINT ck_workflow_nodes_state;

ALTER TABLE workflow_nodes ADD CONSTRAINT ck_workflow_nodes_state CHECK (state IN ('queued', 'running', 'waiting_for_edit', 'completed', 'failed', 'cancelled'));

ALTER TABLE workflow_node_attempts DROP CONSTRAINT ck_workflow_node_attempts_state;

ALTER TABLE workflow_node_attempts ADD CONSTRAINT ck_workflow_node_attempts_state CHECK (state IN ('queued', 'running', 'completed', 'failed', 'cancelled'));

UPDATE alembic_version SET version_num='0017_workflow_cancellation' WHERE alembic_version.version_num = '0016_project_stages';

-- Running upgrade 0017_workflow_cancellation -> 0018_workflow_outbox_leases

ALTER TABLE workflow_outbox ADD COLUMN dispatch_lease_id VARCHAR(64);

ALTER TABLE workflow_outbox ADD COLUMN dispatch_started_at TIMESTAMP WITH TIME ZONE;

CREATE INDEX ix_workflow_outbox_sending_lease ON workflow_outbox (status, dispatch_started_at);

UPDATE workflow_outbox SET dispatch_started_at = created_at WHERE status = 'sending' AND dispatch_started_at IS NULL;

UPDATE alembic_version SET version_num='0018_workflow_outbox_leases' WHERE alembic_version.version_num = '0017_workflow_cancellation';

-- Running upgrade 0018_workflow_outbox_leases -> 0019_short_drama_workflow_v2

UPDATE alembic_version SET version_num='0019_short_drama_workflow_v2' WHERE alembic_version.version_num = '0018_workflow_outbox_leases';

-- Running upgrade 0019_short_drama_workflow_v2 -> 0020_artifact_truth_gate

ALTER TABLE artifacts ADD CONSTRAINT uq_artifacts_project_kind UNIQUE (project_id, kind);

UPDATE alembic_version SET version_num='0020_artifact_truth_gate' WHERE alembic_version.version_num = '0019_short_drama_workflow_v2';

-- Running upgrade 0020_artifact_truth_gate -> 0021_asset_sort_order

ALTER TABLE assets ADD COLUMN sort_order INTEGER;

UPDATE assets SET sort_order = 0 WHERE sort_order IS NULL;

ALTER TABLE assets ALTER COLUMN sort_order SET NOT NULL;

ALTER TABLE assets ADD CONSTRAINT ck_assets_sort_order CHECK (sort_order >= 0);

UPDATE alembic_version SET version_num='0021_asset_sort_order' WHERE alembic_version.version_num = '0020_artifact_truth_gate';

-- Running upgrade 0021_asset_sort_order -> 0022_allow_reused_project_assets

ALTER TABLE assets DROP CONSTRAINT uq_assets_bucket_object_key;

UPDATE alembic_version SET version_num='0022_allow_reused_project_assets' WHERE alembic_version.version_num = '0021_asset_sort_order';

-- Running upgrade 0022_allow_reused_project_assets -> 0023_video_translation

CREATE TABLE project_video_translation_settings (
    project_id VARCHAR(64) NOT NULL, 
    settings JSON NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (project_id), 
    FOREIGN KEY(project_id) REFERENCES projects (id) ON DELETE RESTRICT
);

CREATE TABLE video_translation_segments (
    id VARCHAR(64) NOT NULL, 
    project_id VARCHAR(64) NOT NULL, 
    segment_index INTEGER NOT NULL, 
    start_ms INTEGER NOT NULL, 
    end_ms INTEGER NOT NULL, 
    source_text VARCHAR(4000) NOT NULL, 
    translated_text VARCHAR(4000) NOT NULL, 
    voice_id VARCHAR(128) NOT NULL, 
    voice_overridden BOOLEAN DEFAULT false NOT NULL, 
    speed FLOAT DEFAULT '1' NOT NULL, 
    volume INTEGER DEFAULT '100' NOT NULL, 
    keep_original_sound BOOLEAN DEFAULT false NOT NULL, 
    preview_audio_url VARCHAR(2048), 
    preview_digest VARCHAR(64), 
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    CONSTRAINT uq_translation_segment_index UNIQUE (project_id, segment_index), 
    FOREIGN KEY(project_id) REFERENCES projects (id) ON DELETE RESTRICT
);

CREATE INDEX ix_video_translation_segments_project_id ON video_translation_segments (project_id);

CREATE TABLE video_translation_preview_charges (
    id VARCHAR(64) NOT NULL, 
    project_id VARCHAR(64) NOT NULL, 
    segment_id VARCHAR(64) NOT NULL, 
    idempotency_key VARCHAR(256) NOT NULL, 
    core_task_id VARCHAR(128), 
    credits INTEGER DEFAULT '12' NOT NULL, 
    status VARCHAR(16) DEFAULT 'pending' NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    CONSTRAINT uq_translation_preview_charge UNIQUE (project_id, segment_id, idempotency_key), 
    CONSTRAINT uq_translation_preview_core_task UNIQUE (core_task_id), 
    FOREIGN KEY(project_id) REFERENCES projects (id) ON DELETE RESTRICT, 
    FOREIGN KEY(segment_id) REFERENCES video_translation_segments (id) ON DELETE RESTRICT
);

CREATE INDEX ix_translation_preview_charges_core_task ON video_translation_preview_charges (core_task_id);

UPDATE alembic_version SET version_num='0023_video_translation' WHERE alembic_version.version_num = '0022_allow_reused_project_assets';

-- Running upgrade 0023_video_translation -> 0024_video_translation_price

INSERT INTO product_prices (product, version, credits_per_minute, created_at)
        SELECT 'video_translation', 1, 30, CURRENT_TIMESTAMP
        WHERE NOT EXISTS (
            SELECT 1 FROM product_prices WHERE product = 'video_translation'
        );

UPDATE alembic_version SET version_num='0024_video_translation_price' WHERE alembic_version.version_num = '0023_video_translation';

-- Running upgrade 0024_video_translation_price -> 0025_video_translation_price_30

INSERT INTO product_prices (product, version, credits_per_minute, created_at)
        SELECT 'video_translation', 2, 30, CURRENT_TIMESTAMP
        WHERE EXISTS (
            SELECT 1 FROM product_prices
            WHERE product = 'video_translation' AND version = 1
              AND credits_per_minute = 20
        )
        AND NOT EXISTS (
            SELECT 1 FROM product_prices
            WHERE product = 'video_translation' AND version = 2
        );

UPDATE alembic_version SET version_num='0025_video_translation_price_30' WHERE alembic_version.version_num = '0024_video_translation_price';

-- Running upgrade 0025_video_translation_price_30 -> 0026_video_translation_timing

ALTER TABLE video_translation_segments ADD COLUMN tts_duration_ms INTEGER;

ALTER TABLE video_translation_segments ADD COLUMN timing_fit_status VARCHAR(32) DEFAULT 'pending' NOT NULL;

ALTER TABLE video_translation_segments ADD COLUMN timing_overflow_ms INTEGER DEFAULT '0' NOT NULL;

ALTER TABLE video_translation_segments ADD COLUMN fitted_speed FLOAT;

UPDATE project_video_translation_settings
            SET settings = jsonb_set(
                settings::jsonb,
                '{original_sound_mode}',
                to_jsonb(CASE
                    WHEN settings->>'original_sound_mode' = 'mute'
                        THEN 'translated_voice_only'
                    ELSE 'voice_replacement'
                END::text),
                true
            )
            WHERE settings->>'original_sound_mode' IN ('mute', 'keep', 'preserve');

UPDATE alembic_version SET version_num='0026_video_translation_timing' WHERE alembic_version.version_num = '0025_video_translation_price_30';

-- Running upgrade 0026_video_translation_timing -> 0027_video_translation_voice_replacement_charge

CREATE TABLE video_translation_charges (
    project_id VARCHAR(64) NOT NULL, 
    workflow_id VARCHAR(64) NOT NULL, 
    price_version INTEGER NOT NULL, 
    total_source_seconds INTEGER NOT NULL, 
    billed_minutes INTEGER NOT NULL, 
    base_credits_per_minute INTEGER NOT NULL, 
    original_sound_mode VARCHAR(32) NOT NULL, 
    voice_replacement_credits_per_minute INTEGER NOT NULL, 
    base_credits INTEGER NOT NULL, 
    voice_replacement_credits INTEGER NOT NULL, 
    total_credits INTEGER NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (project_id), 
    CONSTRAINT ck_translation_charge_source_seconds_positive CHECK (total_source_seconds > 0), 
    CONSTRAINT ck_translation_charge_minutes_positive CHECK (billed_minutes > 0), 
    CONSTRAINT ck_translation_charge_base_rate_positive CHECK (base_credits_per_minute > 0), 
    CONSTRAINT ck_translation_charge_surcharge_rate_nonnegative CHECK (voice_replacement_credits_per_minute >= 0), 
    CONSTRAINT ck_translation_charge_base_nonnegative CHECK (base_credits >= 0), 
    CONSTRAINT ck_translation_charge_surcharge_nonnegative CHECK (voice_replacement_credits >= 0), 
    CONSTRAINT ck_translation_charge_total_matches_breakdown CHECK (total_credits = base_credits + voice_replacement_credits), 
    CONSTRAINT ck_translation_charge_audio_mode CHECK (original_sound_mode IN ('voice_replacement', 'translated_voice_only')), 
    FOREIGN KEY(project_id) REFERENCES projects (id) ON DELETE RESTRICT, 
    UNIQUE (workflow_id), 
    FOREIGN KEY(workflow_id) REFERENCES workflows (id) ON DELETE RESTRICT
);

UPDATE alembic_version SET version_num='0027_video_translation_voice_replacement_charge' WHERE alembic_version.version_num = '0026_video_translation_timing';

COMMIT;

