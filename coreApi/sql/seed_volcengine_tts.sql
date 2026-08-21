-- 火山引擎豆包 TTS 的可执行 Core 音色目录。
-- 真实 appid/token 只允许放在私有 config.toml 的
-- [provider_secrets].volcengine JSON 字符串中，不能写入数据库或本文件。
BEGIN;

INSERT INTO core_providers (
  id, code, name, enabled, secret_ref, settings, limits, created_at, updated_at
) VALUES (
  'provider_volcengine_tts',
  'volcengine',
  '火山引擎豆包语音',
  TRUE,
  'volcengine',
  '{"tts_endpoint":"https://openspeech.bytedance.com/api/v1/tts","cluster":"volcano_tts"}'::jsonb,
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

WITH provider AS (
  SELECT id FROM core_providers WHERE code = 'volcengine'
), voices (
  voice_id, provider_voice_code, name, gender, styles
) AS (
  VALUES
    ('voice_volcengine_cancan_v2', 'BV700_V2_streaming', '灿灿 2.0', 'female', '["narration"]'::jsonb),
    ('voice_volcengine_qingcang_v2', 'BV701_V2_streaming', '擎苍 2.0', 'male', '["narration"]'::jsonb),
    ('voice_volcengine_general_f_v2', 'BV001_V2_streaming', '通用女声 2.0', 'female', '[]'::jsonb),
    ('voice_volcengine_general_m', 'BV002_streaming', '通用男声', 'male', '[]'::jsonb),
    ('voice_volcengine_explain_m', 'BV410_streaming', '活力解说男', 'male', '["narration"]'::jsonb),
    ('voice_volcengine_movie_m', 'BV411_streaming', '影视解说小帅', 'male', '["narration"]'::jsonb),
    ('voice_volcengine_movie_f', 'BV412_streaming', '影视解说小美', 'female', '["narration"]'::jsonb),
    ('voice_volcengine_calm_m', 'BV142_streaming', '沉稳解说男', 'male', '["narration"]'::jsonb),
    ('voice_volcengine_youth_m', 'BV123_streaming', '阳光青年', 'male', '[]'::jsonb),
    ('voice_volcengine_gentle_f', 'BV104_streaming', '温柔淑女', 'female', '[]'::jsonb),
    ('voice_volcengine_knowledge_f', 'BV009_streaming', '知性女声', 'female', '[]'::jsonb),
    ('voice_volcengine_dubbing_m', 'BV408_streaming', '译制片男声', 'male', '["narration"]'::jsonb)
)
INSERT INTO core_voices (
  voice_id, provider_id, provider_voice_code, name, languages, gender, styles,
  sample_url, supported_formats, supported_sample_rates, enabled, created_at, updated_at
)
SELECT
  voices.voice_id,
  provider.id,
  voices.provider_voice_code,
  voices.name,
  '["zh-CN","en","ja","ko","de","fr","es","pt","ru","vi","th","id","ar"]'::jsonb,
  voices.gender,
  voices.styles,
  NULL,
  '["wav"]'::jsonb,
  '[16000]'::jsonb,
  TRUE,
  NOW(), NOW()
FROM voices CROSS JOIN provider
ON CONFLICT (provider_id, provider_voice_code) DO UPDATE SET
  name = EXCLUDED.name,
  languages = EXCLUDED.languages,
  gender = EXCLUDED.gender,
  styles = EXCLUDED.styles,
  supported_formats = EXCLUDED.supported_formats,
  supported_sample_rates = EXCLUDED.supported_sample_rates,
  enabled = TRUE,
  updated_at = NOW();

COMMIT;
