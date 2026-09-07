-- 火山方舟 LLM 的短剧分析/文案能力目录。
-- API Key 与实际 Endpoint ID / Model ID 只能放在私有 config.toml 的
-- volcengine_ark_* 字段中；本文件中的 provider_model_code 只是配置占位标记。
BEGIN;

INSERT INTO core_providers (
  id, code, name, enabled, secret_ref, settings, limits, created_at, updated_at
) VALUES (
  'provider_volcengine_ark',
  'volcengine_ark',
  '火山方舟（豆包）',
  TRUE,
  'volcengine_ark',
  '{"prompt_category":"short_drama_narration"}'::jsonb,
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
  'model_volcengine_ark',
  'provider_volcengine_ark',
  '__configured_in_toml__',
  '火山方舟（短剧分析）',
  '["audio_understanding","video_analysis","script_generation"]'::jsonb,
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
