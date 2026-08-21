-- 阿里云百炼 Qwen 的 Core 能力目录。真实 API Key 只能放在 config.toml 的
-- [provider_secrets].aliyun_dashscope，绝不能写入本 SQL 或数据库。
BEGIN;

INSERT INTO core_providers (
  id, code, name, enabled, secret_ref, settings, limits, created_at, updated_at
) VALUES (
  'provider_aliyun_dashscope',
  'aliyun',
  '阿里云百炼（Qwen）',
  TRUE,
  'aliyun_dashscope',
  '{"base_url":"https://dashscope.aliyuncs.com/compatible-mode/v1","prompt_category":"short_drama_narration"}'::jsonb,
  '{"timeout_seconds":120}'::jsonb,
  NOW(), NOW()
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
  NOW(), NOW()
)
ON CONFLICT (provider_id, provider_model_code) DO UPDATE SET
  name = EXCLUDED.name,
  capability_types = EXCLUDED.capability_types,
  languages = EXCLUDED.languages,
  limits = EXCLUDED.limits,
  enabled = TRUE,
  updated_at = NOW();

COMMIT;
