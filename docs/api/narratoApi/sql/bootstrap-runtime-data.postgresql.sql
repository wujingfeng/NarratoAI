-- NarratoAI Business API 运行期基础数据（PostgreSQL）
--
-- 前置条件：已执行 Alembic schema migrations 至当前 head（0032）。
-- 本文件可重复执行：不会覆盖既有价格版本或既有工作流模板快照。
--
-- 当前产品标识必须使用数据库内部值 short_drama_narration，
-- 而不是 Web 请求中的 short-drama-narration。

BEGIN;

-- 1. 短剧解说产品报价。项目报价与启动均依赖此记录。
INSERT INTO product_prices (product, version, credits_per_minute, created_at)
VALUES ('short_drama_narration', 1, 20, NOW())
ON CONFLICT (product, version) DO NOTHING;

-- 2. 短剧解说工作流模板快照。项目启动时会冻结最新快照并实例化节点。
INSERT INTO workflow_template_snapshots (
    id,
    template_name,
    version,
    definition,
    created_at
)
VALUES (
    'tpl_short_drama_narration_v1',
    'short_drama_narration',
    'short_drama_narration_v1',
    '{
      "nodes": [
        {"name": "media_probe", "depends_on": []},
        {"name": "asr", "depends_on": ["media_probe"]},
        {"name": "video_analysis", "depends_on": ["media_probe", "asr"]},
        {"name": "script_generation", "depends_on": ["video_analysis"]},
        {"name": "waiting_for_edit", "depends_on": ["script_generation"], "retryable": false, "manual_gate": true},
        {"name": "tts", "depends_on": ["waiting_for_edit"]},
        {"name": "subtitle", "depends_on": ["tts"]},
        {"name": "video_render", "depends_on": ["subtitle"]},
        {"name": "publish_artifacts", "depends_on": ["video_render"]}
      ]
    }'::jsonb,
    NOW()
)
ON CONFLICT (template_name, version) DO NOTHING;

-- V2 与当前 Business/Core 的可执行节点一致；V1 保留给历史工作流只读追溯。
INSERT INTO workflow_template_snapshots (id, template_name, version, definition, created_at)
VALUES (
    'tpl_short_drama_narration_v2',
    'short_drama_narration',
    'short_drama_narration_v2',
    '{
      "nodes": [
        {"name": "subtitle_recognition", "depends_on": []},
        {"name": "plot_structure", "depends_on": ["subtitle_recognition"]},
        {"name": "conflict_highlights", "depends_on": ["plot_structure"]},
        {"name": "highlight_scoring", "depends_on": ["conflict_highlights"]},
        {"name": "script_generation", "depends_on": ["highlight_scoring"]},
        {"name": "waiting_for_edit", "depends_on": ["script_generation"], "retryable": false, "manual_gate": true},
        {"name": "video_render", "depends_on": ["waiting_for_edit"]},
        {"name": "publish_artifacts", "depends_on": ["video_render"], "retryable": false, "manual_gate": true}
      ]
    }'::jsonb,
    NOW()
)
ON CONFLICT (template_name, version) DO NOTHING;

-- 用户余额不应在此处通过 SQL 直接改写：新注册用户会自动获得 100 创作点，
-- 运营充值请使用 `python -m narrato_api.cli credits grant`，以同时写入 credit_accounts 与 credit_ledger。

-- Video translation: independent product price and recoverable workflow.
INSERT INTO product_prices (product, version, credits_per_minute, created_at)
VALUES ('video_translation', 1, 30, NOW()) ON CONFLICT (product, version) DO NOTHING;
INSERT INTO product_prices (product, version, credits_per_minute, created_at)
VALUES ('video_translation', 2, 30, NOW()) ON CONFLICT (product, version) DO NOTHING;
INSERT INTO workflow_template_snapshots (id, template_name, version, definition, created_at)
VALUES ('tpl_video_translation_v1', 'video_translation', 'video_translation_v1',
'{"nodes":[{"name":"subtitle_recognition","depends_on":[]},{"name":"subtitle_translation","depends_on":["subtitle_recognition"]},{"name":"subtitle_rewrite","depends_on":["subtitle_translation"]},{"name":"tts","depends_on":["subtitle_translation"]},{"name":"video_render","depends_on":["tts"]},{"name":"publish_artifacts","depends_on":["video_render"]}]}'::jsonb, NOW())
ON CONFLICT (template_name, version) DO NOTHING;

COMMIT;

-- 验证：两种产品的价格和工作流模板都必须至少返回一行。
SELECT product, version, credits_per_minute, created_at
FROM product_prices
WHERE product IN ('short_drama_narration', 'video_translation')
ORDER BY product, version DESC;

SELECT id, template_name, version, definition, created_at
FROM workflow_template_snapshots
WHERE template_name IN ('short_drama_narration', 'video_translation')
ORDER BY template_name, created_at DESC;

-- Generic model runtime seed. Provider API keys and model IDs are deliberately empty
-- and disabled until operations configures a real Volc Ark account.
INSERT INTO models (
  id, display_name, model_type, description, category, sort_order, is_enabled,
  is_default, created_at, updated_at
) VALUES
  ('seedance-2.5', 'Seedance 2.5', 'video', '支持图片、视频、音频与文本参考的视频生成', 'Seedance', 30, false, true, NOW(), NOW()),
  ('seedream', 'Seedream', 'image', '火山方舟图片生成模型', 'Seedream', 20, false, true, NOW(), NOW()),
  ('doubao-llm', 'Doubao LLM', 'llm', '火山方舟多模态对话模型', 'Doubao', 10, false, true, NOW(), NOW())
ON CONFLICT (id) DO NOTHING;

INSERT INTO model_play_modes (
  id, model_id, code, display_name, default_credits, active_provider_id,
  supports_generate_audio, is_enabled, is_default, sort_order, created_at, updated_at
) VALUES
  ('mode_seedance_reference', 'seedance-2.5', 'reference_to_video', '参考生视频', 0, NULL, true, false, true, 30, NOW(), NOW()),
  ('mode_seedream_reference', 'seedream', 'reference_to_image', '参考生图', 0, NULL, false, false, true, 20, NOW(), NOW()),
  ('mode_doubao_chat', 'doubao-llm', 'chat', '多模态对话', 0, NULL, false, false, true, 10, NOW(), NOW())
ON CONFLICT (id) DO NOTHING;

INSERT INTO model_play_mode_providers (
  id, play_mode_id, provider_code, provider_model_id, submit_url,
  status_query_url, status_query_method, api_key, is_enabled, created_at, updated_at
) VALUES
  ('provider_seedance_reference', 'mode_seedance_reference', 'volcengine', 'replace-with-volcengine-seedance-model-id',
   'https://ark.cn-beijing.volces.com/api/v3/contents/generations/tasks',
   'https://ark.cn-beijing.volces.com/api/v3/contents/generations/tasks/{task_id}', 'GET', '', false, NOW(), NOW()),
  ('provider_seedream_reference', 'mode_seedream_reference', 'volcengine', 'replace-with-volcengine-seedream-model-id',
   'https://ark.cn-beijing.volces.com/api/v3/images/generations', NULL, 'GET', '', false, NOW(), NOW()),
  ('provider_doubao_chat', 'mode_doubao_chat', 'volcengine', 'replace-with-volcengine-llm-model-id',
   'https://ark.cn-beijing.volces.com/api/v3/chat/completions', NULL, 'GET', '', false, NOW(), NOW())
ON CONFLICT (id) DO NOTHING;

UPDATE model_play_modes
SET active_provider_id = CASE id
  WHEN 'mode_seedance_reference' THEN 'provider_seedance_reference'
  WHEN 'mode_seedream_reference' THEN 'provider_seedream_reference'
  WHEN 'mode_doubao_chat' THEN 'provider_doubao_chat'
  ELSE active_provider_id
END
WHERE id IN ('mode_seedance_reference', 'mode_seedream_reference', 'mode_doubao_chat');

-- Input rules. max_text_units counts Chinese characters plus English words.
INSERT INTO model_play_mode_rules (
  id, play_mode_id, rule_kind, input_type, is_supported, is_required, max_count,
  max_file_size_bytes, max_duration_seconds, max_text_units, supports_mention,
  sort_order, created_at, updated_at
) VALUES
  ('rule_seedance_text', 'mode_seedance_reference', 'input_constraint', 'text', true, false, NULL, NULL, NULL, 1000, false, 4, NOW(), NOW()),
  ('rule_seedance_image', 'mode_seedance_reference', 'input_constraint', 'image', true, false, 30, 31457280, NULL, NULL, true, 3, NOW(), NOW()),
  ('rule_seedance_video', 'mode_seedance_reference', 'input_constraint', 'video', true, false, 10, NULL, 30, NULL, true, 2, NOW(), NOW()),
  ('rule_seedance_audio', 'mode_seedance_reference', 'input_constraint', 'audio', true, false, 10, NULL, 30, NULL, true, 1, NOW(), NOW()),
  ('rule_seedream_text', 'mode_seedream_reference', 'input_constraint', 'text', true, true, NULL, NULL, NULL, 600, false, 2, NOW(), NOW()),
  ('rule_seedream_image', 'mode_seedream_reference', 'input_constraint', 'image', true, false, 10, 31457280, NULL, NULL, true, 1, NOW(), NOW()),
  ('rule_doubao_text', 'mode_doubao_chat', 'input_constraint', 'text', true, true, NULL, NULL, NULL, 8000, false, 4, NOW(), NOW()),
  ('rule_doubao_image', 'mode_doubao_chat', 'input_constraint', 'image', true, false, 20, 31457280, NULL, NULL, true, 3, NOW(), NOW()),
  ('rule_doubao_video', 'mode_doubao_chat', 'input_constraint', 'video', true, false, 10, NULL, 600, NULL, true, 2, NOW(), NOW()),
  ('rule_doubao_audio', 'mode_doubao_chat', 'input_constraint', 'audio', true, false, 10, NULL, 600, NULL, true, 1, NOW(), NOW())
ON CONFLICT (id) DO NOTHING;

INSERT INTO model_play_mode_rules (
  id, play_mode_id, rule_kind, is_supported, output_option_type, resolution,
  ratio, duration_seconds, sort_order, created_at, updated_at
) VALUES
  ('option_seedance_resolution', 'mode_seedance_reference', 'output_option', true, 'resolution', ARRAY['480P', '720P', '1080P', '4K'], NULL, NULL, 3, NOW(), NOW()),
  ('option_seedance_ratio', 'mode_seedance_reference', 'output_option', true, 'ratio', NULL, ARRAY['adaptive', '9:16', '16:9'], NULL, 2, NOW(), NOW()),
  ('option_seedance_duration', 'mode_seedance_reference', 'output_option', true, 'duration', NULL, NULL, ARRAY['adaptive', '4', '5', '6', '7', '8', '15', '20', '30'], 1, NOW(), NOW()),
  ('option_seedream_resolution', 'mode_seedream_reference', 'output_option', true, 'resolution', ARRAY['1K', '2K'], NULL, NULL, 2, NOW(), NOW())
ON CONFLICT (id) DO NOTHING;

-- 直接配置用户扣除积分，不使用金额或汇率。启用供应商前填入真实积分值；
-- 提交任务时，规则会复制到 model_task_charges 作为收费快照。
INSERT INTO model_play_mode_provider_prices (
  id, provider_id, resolution, billing_unit,
  per_million_input_credits, per_million_output_credits,
  per_usage_credits, per_second_credits,
  is_enabled, created_at, updated_at
) VALUES
  ('price_seedance_720p_second', 'provider_seedance_reference', '720p', 'second', NULL, NULL, NULL, 0, false, NOW(), NOW()),
  ('price_seedance_480p_second', 'provider_seedance_reference', '480p', 'second', NULL, NULL, NULL, 0, false, NOW(), NOW()),
  ('price_seedream_2k_usage', 'provider_seedream_reference', '2K', 'usage', NULL, NULL, 0, NULL, false, NOW(), NOW()),
  ('price_seedream_1k_usage', 'provider_seedream_reference', '1K', 'usage', NULL, NULL, 0, NULL, false, NOW(), NOW()),
  ('price_doubao_token', 'provider_doubao_chat', NULL, 'token', 0, 0, NULL, NULL, false, NOW(), NOW())
ON CONFLICT (id) DO NOTHING;
