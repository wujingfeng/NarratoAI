-- NarratoAI Core API PostgreSQL 完整建表脚本。
-- 由 Alembic migrations 生成：alembic upgrade head --sql。
-- 执行前请连接目标 Core 数据库；本脚本会创建表、索引、约束及 alembic_version 版本记录。
-- 公共字段约定：id 为业务主键；created_at/updated_at 使用 UTC 时间；status 为受约束的状态枚举；
-- JSON 字段保存可扩展快照、输入输出或错误详情，不取代可查询的核心关系字段。

BEGIN;

CREATE TABLE alembic_version (
    version_num VARCHAR(64) NOT NULL,
    CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num)
);

-- Running upgrade  -> 0001_core_base

INSERT INTO alembic_version (version_num) VALUES ('0001_core_base') RETURNING alembic_version.version_num;

-- Running upgrade 0001_core_base -> 0002_core_tasks

CREATE TABLE core_tasks (
    id VARCHAR(40) NOT NULL,
    task_type VARCHAR(80) NOT NULL,
    caller VARCHAR(120) NOT NULL,
    caller_task_id VARCHAR(80),
    idempotency_scope VARCHAR(512) NOT NULL,
    idempotency_key VARCHAR(255) NOT NULL,
    request_digest VARCHAR(64) NOT NULL,
    input_snapshot JSON NOT NULL,
    status VARCHAR(10) NOT NULL,
    phase VARCHAR(80),
    progress INTEGER NOT NULL,
    state_version INTEGER NOT NULL,
    current_attempt_no INTEGER NOT NULL,
    max_retries INTEGER NOT NULL,
    error JSON,
    result JSON,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL,
    started_at TIMESTAMP WITH TIME ZONE,
    finished_at TIMESTAMP WITH TIME ZONE,
    PRIMARY KEY (id),
    CONSTRAINT uq_core_tasks_idempotency_scope UNIQUE (idempotency_scope),
    CONSTRAINT core_task_status CHECK (status IN ('queued', 'running', 'retry_wait', 'succeeded', 'failed'))
);

CREATE INDEX ix_core_tasks_status_created_at ON core_tasks (status, created_at);

CREATE TABLE core_task_attempts (
    id VARCHAR(40) NOT NULL,
    core_task_id VARCHAR(40) NOT NULL,
    attempt_no INTEGER NOT NULL,
    status VARCHAR(9) NOT NULL,
    lease_token VARCHAR(128) NOT NULL,
    lease_version INTEGER NOT NULL,
    lease_expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
    heartbeat_at TIMESTAMP WITH TIME ZONE NOT NULL,
    started_at TIMESTAMP WITH TIME ZONE NOT NULL,
    finished_at TIMESTAMP WITH TIME ZONE,
    error JSON,
    late_result_audit JSON,
    PRIMARY KEY (id),
    FOREIGN KEY(core_task_id) REFERENCES core_tasks (id) ON DELETE CASCADE,
    CONSTRAINT uq_core_task_attempts_task_no UNIQUE (core_task_id, attempt_no),
    CONSTRAINT core_attempt_status CHECK (status IN ('running', 'succeeded', 'failed', 'expired'))
);

CREATE INDEX ix_core_task_attempts_lease_expiry ON core_task_attempts (status, lease_expires_at);

CREATE TABLE callback_outbox (
    id VARCHAR(40) NOT NULL,
    event_id VARCHAR(80) NOT NULL,
    core_task_id VARCHAR(40) NOT NULL,
    attempt_no INTEGER NOT NULL,
    state_version INTEGER NOT NULL,
    payload JSON NOT NULL,
    status VARCHAR(7) NOT NULL,
    attempt_count INTEGER NOT NULL,
    next_attempt_at TIMESTAMP WITH TIME ZONE NOT NULL,
    sent_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL,
    PRIMARY KEY (id),
    FOREIGN KEY(core_task_id) REFERENCES core_tasks (id) ON DELETE CASCADE,
    CONSTRAINT uq_callback_outbox_event_id UNIQUE (event_id),
    CONSTRAINT uq_callback_outbox_task_state_version UNIQUE (core_task_id, state_version),
    CONSTRAINT callback_outbox_status CHECK (status IN ('pending', 'sent'))
);

CREATE INDEX ix_callback_outbox_pending ON callback_outbox (status, next_attempt_at);

UPDATE alembic_version SET version_num='0002_core_tasks' WHERE alembic_version.version_num = '0001_core_base';

-- Running upgrade 0002_core_tasks -> 0003_core_capabilities

CREATE TABLE core_providers (
    id VARCHAR(40) NOT NULL,
    code VARCHAR(80) NOT NULL,
    name VARCHAR(160) NOT NULL,
    enabled BOOLEAN NOT NULL,
    secret_ref VARCHAR(160) NOT NULL,
    settings JSON NOT NULL,
    limits JSON NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL,
    PRIMARY KEY (id),
    CONSTRAINT uq_core_providers_code UNIQUE (code)
);

CREATE TABLE core_models (
    model_id VARCHAR(40) NOT NULL,
    provider_id VARCHAR(40) NOT NULL,
    provider_model_code VARCHAR(160) NOT NULL,
    name VARCHAR(160) NOT NULL,
    capability_types JSON NOT NULL,
    languages JSON NOT NULL,
    limits JSON NOT NULL,
    enabled BOOLEAN NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL,
    PRIMARY KEY (model_id),
    FOREIGN KEY(provider_id) REFERENCES core_providers (id) ON DELETE CASCADE,
    CONSTRAINT uq_core_models_provider_code UNIQUE (provider_id, provider_model_code)
);

CREATE INDEX ix_core_models_provider_enabled ON core_models (provider_id, enabled);

CREATE TABLE core_voices (
    voice_id VARCHAR(40) NOT NULL,
    provider_id VARCHAR(40) NOT NULL,
    provider_voice_code VARCHAR(160) NOT NULL,
    name VARCHAR(160) NOT NULL,
    languages JSON NOT NULL,
    gender VARCHAR(32),
    styles JSON NOT NULL,
    sample_url VARCHAR(2048),
    supported_formats JSON NOT NULL,
    supported_sample_rates JSON NOT NULL,
    enabled BOOLEAN NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL,
    PRIMARY KEY (voice_id),
    FOREIGN KEY(provider_id) REFERENCES core_providers (id) ON DELETE CASCADE,
    CONSTRAINT uq_core_voices_provider_code UNIQUE (provider_id, provider_voice_code)
);

CREATE INDEX ix_core_voices_provider_enabled ON core_voices (provider_id, enabled);

UPDATE alembic_version SET version_num='0003_core_capabilities' WHERE alembic_version.version_num = '0002_core_tasks';

-- Running upgrade 0003_core_capabilities -> 0004_core_artifacts

ALTER TABLE core_tasks ADD COLUMN initial_response JSON DEFAULT '{}' NOT NULL;

CREATE TABLE core_artifacts (
    id VARCHAR(40) NOT NULL,
    core_task_id VARCHAR(40) NOT NULL,
    attempt_no INTEGER NOT NULL,
    kind VARCHAR(80) NOT NULL,
    bucket VARCHAR(255) NOT NULL,
    object_key VARCHAR(1024) NOT NULL,
    url VARCHAR(2048) NOT NULL,
    content_type VARCHAR(255) NOT NULL,
    size INTEGER NOT NULL,
    checksum VARCHAR(80),
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    PRIMARY KEY (id),
    FOREIGN KEY(core_task_id) REFERENCES core_tasks (id) ON DELETE CASCADE,
    CONSTRAINT fk_core_artifacts_task_attempt FOREIGN KEY(core_task_id, attempt_no) REFERENCES core_task_attempts (core_task_id, attempt_no) ON DELETE CASCADE,
    CONSTRAINT ck_core_artifacts_attempt_positive CHECK (attempt_no > 0),
    CONSTRAINT ck_core_artifacts_size_positive CHECK (size > 0),
    CONSTRAINT uq_core_artifacts_object_key UNIQUE (object_key)
);

CREATE INDEX ix_core_artifacts_task_attempt ON core_artifacts (core_task_id, attempt_no);

CREATE TABLE core_dispatch_outbox (
    id VARCHAR(40) NOT NULL,
    core_task_id VARCHAR(40) NOT NULL,
    state_version INTEGER NOT NULL,
    status VARCHAR(7) NOT NULL,
    available_at TIMESTAMP WITH TIME ZONE NOT NULL,
    attempt_count INTEGER NOT NULL,
    last_error VARCHAR(80),
    sent_at TIMESTAMP WITH TIME ZONE,
    recover_after TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL,
    PRIMARY KEY (id),
    FOREIGN KEY(core_task_id) REFERENCES core_tasks (id) ON DELETE CASCADE,
    CONSTRAINT uq_core_dispatch_task_state UNIQUE (core_task_id, state_version),
    CONSTRAINT core_dispatch_status CHECK (status IN ('pending', 'sent'))
);

CREATE INDEX ix_core_dispatch_pending ON core_dispatch_outbox (status, available_at);

CREATE INDEX ix_core_dispatch_recovery ON core_dispatch_outbox (status, recover_after);

UPDATE core_tasks SET initial_response = json_build_object('core_task_id', id, 'status', 'queued');

INSERT INTO core_dispatch_outbox (
                id, core_task_id, state_version, status, available_at,
                attempt_count, last_error, sent_at, recover_after, created_at, updated_at
            )
            SELECT id, id, state_version, 'pending', COALESCE(updated_at, created_at),
                   0, NULL, NULL, NULL, created_at, updated_at
            FROM core_tasks
            WHERE status IN ('queued', 'retry_wait');

UPDATE alembic_version SET version_num='0004_core_artifacts' WHERE alembic_version.version_num = '0003_core_capabilities';

-- Running upgrade 0004_core_artifacts -> 0005_core_task_checkpoints

ALTER TABLE core_tasks ADD COLUMN retry_count INTEGER DEFAULT '0' NOT NULL;

CREATE TABLE core_task_checkpoints (
    id VARCHAR(40) NOT NULL,
    core_task_id VARCHAR(40) NOT NULL,
    stage VARCHAR(80) NOT NULL,
    stage_version INTEGER NOT NULL,
    input_digest VARCHAR(64) NOT NULL,
    status VARCHAR(7) NOT NULL,
    manifest JSON NOT NULL,
    created_by_attempt_no INTEGER NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    completed_at TIMESTAMP WITH TIME ZONE NOT NULL,
    invalidated_at TIMESTAMP WITH TIME ZONE,
    PRIMARY KEY (id),
    CONSTRAINT ck_core_task_checkpoint_attempt_positive CHECK (created_by_attempt_no > 0),
    FOREIGN KEY(core_task_id) REFERENCES core_tasks (id) ON DELETE CASCADE,
    CONSTRAINT uq_core_task_checkpoint_identity UNIQUE (core_task_id, stage, stage_version, input_digest),
    CONSTRAINT core_checkpoint_status CHECK (status IN ('ready', 'invalid'))
);

CREATE INDEX ix_core_task_checkpoints_lookup ON core_task_checkpoints (core_task_id, stage, status);

CREATE TABLE core_checkpoint_artifacts (
    id VARCHAR(40) NOT NULL,
    checkpoint_id VARCHAR(40) NOT NULL,
    kind VARCHAR(80) NOT NULL,
    relative_path VARCHAR(255) NOT NULL,
    content_type VARCHAR(255) NOT NULL,
    size INTEGER NOT NULL,
    checksum VARCHAR(80) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    PRIMARY KEY (id),
    CONSTRAINT ck_core_checkpoint_artifact_size_positive CHECK (size > 0),
    FOREIGN KEY(checkpoint_id) REFERENCES core_task_checkpoints (id) ON DELETE CASCADE,
    CONSTRAINT uq_core_checkpoint_artifact_kind UNIQUE (checkpoint_id, kind)
);

CREATE INDEX ix_core_checkpoint_artifacts_checkpoint ON core_checkpoint_artifacts (checkpoint_id);

UPDATE alembic_version SET version_num='0005_core_task_checkpoints' WHERE alembic_version.version_num = '0004_core_artifacts';

-- Running upgrade 0005_core_task_checkpoints -> 0006_volcengine_multilingual_voices

UPDATE core_voices SET languages = '["zh-CN","en","ja","ko","de","fr","es","pt","ru","vi","th","id","ar"]'::jsonb WHERE provider_id = (SELECT id FROM core_providers WHERE code = 'volcengine');

UPDATE alembic_version SET version_num='0006_volcengine_multilingual_voices' WHERE alembic_version.version_num = '0005_core_task_checkpoints';

-- Running upgrade 0006_volcengine_multilingual_voices -> 0007_asr_provider_jobs

CREATE TABLE asr_provider_jobs (
    id VARCHAR(40) NOT NULL,
    core_task_id VARCHAR(40) NOT NULL,
    source_index INTEGER NOT NULL,
    source_asset_id VARCHAR(80) NOT NULL,
    provider VARCHAR(40) NOT NULL,
    provider_task_id VARCHAR(160),
    callback_key VARCHAR(128) NOT NULL,
    prepared_audio_url VARCHAR(2048),
    status VARCHAR(24) NOT NULL,
    response_payload JSON,
    error JSON,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL,
    PRIMARY KEY (id),
    CONSTRAINT ck_asr_provider_jobs_status CHECK (status IN ('preparing', 'submitted', 'succeeded', 'failed')),
    FOREIGN KEY(core_task_id) REFERENCES core_tasks (id) ON DELETE CASCADE,
    CONSTRAINT uq_asr_provider_jobs_task_source UNIQUE (core_task_id, source_index),
    CONSTRAINT uq_asr_provider_jobs_remote UNIQUE (provider, provider_task_id),
    CONSTRAINT uq_asr_provider_jobs_callback_key UNIQUE (callback_key)
);

CREATE INDEX ix_asr_provider_jobs_status ON asr_provider_jobs (status, updated_at);

UPDATE alembic_version SET version_num='0007_asr_provider_jobs' WHERE alembic_version.version_num = '0006_volcengine_multilingual_voices';

-- ============================================================================
-- 数据字典：Core 任务、能力目录与产物
-- ============================================================================
COMMENT ON TABLE alembic_version IS 'Alembic 数据库迁移版本记录。';
COMMENT ON TABLE core_tasks IS 'Core 原子能力任务主表；保存调用方、幂等范围、输入快照、执行状态与最终结果。';
COMMENT ON COLUMN core_tasks.id IS '带 ctask_ 前缀的 Core 任务业务主键。';
COMMENT ON COLUMN core_tasks.idempotency_scope IS '调用方、请求路径与幂等键组成的唯一请求作用域。';
COMMENT ON COLUMN core_tasks.input_snapshot IS '创建任务时冻结的请求输入 JSON 快照。';
COMMENT ON COLUMN core_tasks.state_version IS '任务状态单调版本，用于拒绝陈旧回调和重复推进。';
COMMENT ON COLUMN core_tasks.initial_response IS '首次创建响应的持久化 JSON，保证重复请求返回稳定结果。';
COMMENT ON TABLE core_task_attempts IS 'Core Worker 执行尝试表；保存租约、心跳、错误和过期结果审计。';
COMMENT ON COLUMN core_task_attempts.lease_token IS '当前 Worker 持有的租约令牌。';
COMMENT ON COLUMN core_task_attempts.lease_version IS '租约版本，防止旧 attempt 覆盖新 attempt。';
COMMENT ON COLUMN core_task_attempts.late_result_audit IS '过期 attempt 晚到结果的审计 JSON，不改变当前任务状态。';
COMMENT ON TABLE callback_outbox IS 'Core 向 Business API 投递状态回调的可重试 Outbox。';
COMMENT ON COLUMN callback_outbox.event_id IS '回调事件唯一标识，同时作为 HTTP 幂等键。';
COMMENT ON COLUMN callback_outbox.payload IS '发送给 Business API 的回调请求 JSON。';
COMMENT ON TABLE core_providers IS '第三方能力供应商配置；只保存 secret_ref，不保存真实密钥。';
COMMENT ON TABLE core_models IS '标准化模型目录，映射供应商模型代码到稳定 model_id。';
COMMENT ON TABLE core_voices IS '标准化音色目录，映射供应商音色代码到稳定 voice_id。';
COMMENT ON TABLE core_artifacts IS 'Core 任务生成或登记的 OSS/CDN 产物。';
COMMENT ON COLUMN core_artifacts.object_key IS '对象存储中的唯一对象键。';
COMMENT ON COLUMN core_artifacts.url IS '可访问的 CDN 或对象 URL。';
COMMENT ON TABLE core_dispatch_outbox IS 'Core 任务创建后的可靠唤醒 Outbox，支持失败恢复和重复投递保护。';
COMMENT ON COLUMN core_dispatch_outbox.available_at IS '允许下一次投递的时间。';
COMMENT ON COLUMN core_dispatch_outbox.recover_after IS '发送中记录被判定为可恢复的时间。';

-- 完整字段数据字典；枚举字段在注释中列出可取值及含义。
COMMENT ON COLUMN alembic_version.version_num IS '当前已应用的 Alembic 迁移版本号。';

COMMENT ON COLUMN core_tasks.id IS '带 ctask_ 前缀的 Core 任务业务主键。';
COMMENT ON COLUMN core_tasks.task_type IS '原子能力类型：media_probe=媒体探测；asr=通用语音识别；audio_understanding=短剧内嵌音频理解；video_analysis=视频分析；script_generation=文案生成；tts=语音合成；subtitle=字幕处理；video_render=视频渲染。';
COMMENT ON COLUMN core_tasks.caller IS '创建任务的调用方服务标识。';
COMMENT ON COLUMN core_tasks.caller_task_id IS '调用方的关联任务标识；无关联时为空。';
COMMENT ON COLUMN core_tasks.idempotency_key IS '调用方提交的原始幂等键。';
COMMENT ON COLUMN core_tasks.request_digest IS '规范化请求体的 SHA-256 摘要，用于检测幂等冲突。';
COMMENT ON COLUMN core_tasks.status IS '任务状态：queued=待投递；running=执行中；retry_wait=等待重试；succeeded=成功；failed=最终失败。';
COMMENT ON COLUMN core_tasks.phase IS '任务当前执行阶段，供进度展示；未开始时为空。';
COMMENT ON COLUMN core_tasks.progress IS '任务进度百分比，范围由任务处理器定义。';
COMMENT ON COLUMN core_tasks.current_attempt_no IS '当前或最近一次执行 attempt 编号；未执行时为 0。';
COMMENT ON COLUMN core_tasks.max_retries IS '允许自动重试的最大次数。';
COMMENT ON COLUMN core_tasks.error IS '规范化错误详情 JSON；成功时为空。';
COMMENT ON COLUMN core_tasks.result IS '规范化结果及产物引用 JSON；未完成时为空。';
COMMENT ON COLUMN core_tasks.created_at IS '任务创建时间（UTC）。';
COMMENT ON COLUMN core_tasks.updated_at IS '任务最后更新时间（UTC）。';
COMMENT ON COLUMN core_tasks.started_at IS '首次开始执行时间（UTC）；未开始时为空。';
COMMENT ON COLUMN core_tasks.finished_at IS '进入终态时间（UTC）；未结束时为空。';

COMMENT ON COLUMN core_task_attempts.id IS 'Core 任务执行尝试主键。';
COMMENT ON COLUMN core_task_attempts.core_task_id IS '所属 Core 任务。';
COMMENT ON COLUMN core_task_attempts.attempt_no IS '同一任务从 1 开始的执行次数。';
COMMENT ON COLUMN core_task_attempts.status IS '尝试状态：running=执行中；succeeded=成功；failed=失败；expired=租约或心跳过期。';
COMMENT ON COLUMN core_task_attempts.lease_expires_at IS '当前租约过期时间（UTC）。';
COMMENT ON COLUMN core_task_attempts.heartbeat_at IS 'Worker 最近一次心跳时间（UTC）。';
COMMENT ON COLUMN core_task_attempts.started_at IS '本次尝试开始时间（UTC）。';
COMMENT ON COLUMN core_task_attempts.finished_at IS '本次尝试终态时间（UTC）；未结束时为空。';
COMMENT ON COLUMN core_task_attempts.error IS '本次尝试的规范化错误 JSON；成功时为空。';

COMMENT ON COLUMN callback_outbox.id IS '回调 Outbox 记录主键。';
COMMENT ON COLUMN callback_outbox.core_task_id IS '需要向 Business 回调的 Core 任务。';
COMMENT ON COLUMN callback_outbox.attempt_no IS '产生该回调的任务尝试编号。';
COMMENT ON COLUMN callback_outbox.state_version IS '产生该回调的任务状态版本。';
COMMENT ON COLUMN callback_outbox.status IS '回调投递状态：pending=待发送；sent=已发送。';
COMMENT ON COLUMN callback_outbox.attempt_count IS '已尝试发送次数。';
COMMENT ON COLUMN callback_outbox.next_attempt_at IS '允许下一次回调尝试的时间（UTC）。';
COMMENT ON COLUMN callback_outbox.sent_at IS '成功发送时间（UTC）；未发送时为空。';
COMMENT ON COLUMN callback_outbox.created_at IS '回调记录创建时间（UTC）。';
COMMENT ON COLUMN callback_outbox.updated_at IS '回调记录最后更新时间（UTC）。';

COMMENT ON COLUMN core_providers.id IS '供应商配置主键。';
COMMENT ON COLUMN core_providers.code IS '供应商稳定代码，例如 volcengine、aliyun。';
COMMENT ON COLUMN core_providers.name IS '供应商展示名称。';
COMMENT ON COLUMN core_providers.enabled IS '是否允许该供应商提供能力。';
COMMENT ON COLUMN core_providers.secret_ref IS '私有 TOML 中真实密钥的引用名，不存储密钥。';
COMMENT ON COLUMN core_providers.settings IS '供应商非敏感运行配置 JSON。';
COMMENT ON COLUMN core_providers.limits IS '供应商限额与超时等限制 JSON。';
COMMENT ON COLUMN core_providers.created_at IS '供应商记录创建时间（UTC）。';
COMMENT ON COLUMN core_providers.updated_at IS '供应商记录最后更新时间（UTC）。';

COMMENT ON COLUMN core_models.model_id IS '对外稳定的模型标识。';
COMMENT ON COLUMN core_models.provider_id IS '所属供应商。';
COMMENT ON COLUMN core_models.provider_model_code IS '供应商侧模型代码。';
COMMENT ON COLUMN core_models.name IS '模型展示名称。';
COMMENT ON COLUMN core_models.capability_types IS '模型支持的能力类型数组 JSON。';
COMMENT ON COLUMN core_models.languages IS '模型支持的语言代码数组 JSON。';
COMMENT ON COLUMN core_models.limits IS '模型输入、输出及并发限制 JSON。';
COMMENT ON COLUMN core_models.enabled IS '是否允许业务层选用该模型。';
COMMENT ON COLUMN core_models.created_at IS '模型记录创建时间（UTC）。';
COMMENT ON COLUMN core_models.updated_at IS '模型记录最后更新时间（UTC）。';

COMMENT ON COLUMN core_voices.voice_id IS '对外稳定的音色标识。';
COMMENT ON COLUMN core_voices.provider_id IS '所属供应商。';
COMMENT ON COLUMN core_voices.provider_voice_code IS '供应商侧音色代码。';
COMMENT ON COLUMN core_voices.name IS '音色展示名称。';
COMMENT ON COLUMN core_voices.languages IS '支持的语言代码数组 JSON。';
COMMENT ON COLUMN core_voices.gender IS '音色性别或声线标签；供应商未提供时为空。';
COMMENT ON COLUMN core_voices.styles IS '支持的表达风格数组 JSON。';
COMMENT ON COLUMN core_voices.sample_url IS '试听音频公开地址；无试听时为空。';
COMMENT ON COLUMN core_voices.supported_formats IS '支持输出音频格式数组 JSON。';
COMMENT ON COLUMN core_voices.supported_sample_rates IS '支持输出采样率数组 JSON。';
COMMENT ON COLUMN core_voices.enabled IS '是否允许业务层选用该音色。';
COMMENT ON COLUMN core_voices.created_at IS '音色记录创建时间（UTC）。';
COMMENT ON COLUMN core_voices.updated_at IS '音色记录最后更新时间（UTC）。';

COMMENT ON COLUMN core_artifacts.id IS 'Core 产物主键。';
COMMENT ON COLUMN core_artifacts.core_task_id IS '生成该产物的 Core 任务。';
COMMENT ON COLUMN core_artifacts.attempt_no IS '生成该产物的任务尝试编号。';
COMMENT ON COLUMN core_artifacts.kind IS '产物类别，例如 video、audio、subtitle、manifest。';
COMMENT ON COLUMN core_artifacts.bucket IS '对象存储 Bucket 名称。';
COMMENT ON COLUMN core_artifacts.content_type IS '产物 MIME 类型。';
COMMENT ON COLUMN core_artifacts.size IS '产物字节大小。';
COMMENT ON COLUMN core_artifacts.checksum IS '可选完整性校验摘要。';
COMMENT ON COLUMN core_artifacts.created_at IS '产物登记时间（UTC）。';

COMMENT ON COLUMN core_dispatch_outbox.id IS 'Core 任务唤醒 Outbox 主键。';
COMMENT ON COLUMN core_dispatch_outbox.core_task_id IS '待唤醒执行的 Core 任务。';
COMMENT ON COLUMN core_dispatch_outbox.state_version IS '创建唤醒事件时的任务状态版本。';
COMMENT ON COLUMN core_dispatch_outbox.status IS '唤醒投递状态：pending=待发送；sent=已发送。';
COMMENT ON COLUMN core_dispatch_outbox.attempt_count IS '已尝试唤醒次数。';
COMMENT ON COLUMN core_dispatch_outbox.last_error IS '最近一次投递错误摘要；无错误时为空。';
COMMENT ON COLUMN core_dispatch_outbox.sent_at IS '成功唤醒投递时间（UTC）；未发送时为空。';
COMMENT ON COLUMN core_dispatch_outbox.created_at IS 'Outbox 记录创建时间（UTC）。';
COMMENT ON COLUMN core_dispatch_outbox.updated_at IS 'Outbox 记录最后更新时间（UTC）。';

INSERT INTO core_providers (
  id, code, name, enabled, secret_ref, settings, limits, created_at, updated_at
) VALUES (
  'provider_aliyun_dashscope',
  'aliyun',
  '阿里云百炼（Qwen）',
  TRUE,
  'aliyun_dashscope',
  '{
    "base_url":"https://llm-r5pat4zegj3dkz3r.cn-beijing.maas.aliyuncs.com/compatible-mode/v1",
    "prompt_category":"short_drama_narration"
  }'::jsonb,
  '{"timeout_seconds":120}'::jsonb,
  NOW(),
  NOW()
)
ON CONFLICT (code) DO UPDATE SET
  name = EXCLUDED.name,
  enabled = TRUE,
  secret_ref = EXCLUDED.secret_ref,
  settings = EXCLUDED.settings,
  limits = EXCLUDED.limits,
  updated_at = NOW();

INSERT INTO core_models (
  model_id, provider_id, provider_model_code, name,
  capability_types, languages, limits, enabled, created_at, updated_at
) VALUES (
  'model_qwen_plus',
  'provider_aliyun_dashscope',
  'qwen-plus',
  '通义千问 Plus（短剧分析）',
  '["video_analysis","script_generation"]'::jsonb,
  '["zh-CN"]'::jsonb,
  '{"max_input_chars":100000,"max_tokens":8192}'::jsonb,
  TRUE,
  NOW(),
  NOW()
)
ON CONFLICT (provider_id, provider_model_code) DO UPDATE SET
  name = EXCLUDED.name,
  capability_types = EXCLUDED.capability_types,
  languages = EXCLUDED.languages,
  limits = EXCLUDED.limits,
  enabled = TRUE,
  updated_at = NOW();

COMMIT;
