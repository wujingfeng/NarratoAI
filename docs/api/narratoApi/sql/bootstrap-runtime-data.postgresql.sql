-- NarratoAI Business API 运行期基础数据（PostgreSQL）
--
-- 前置条件：已执行 Alembic schema migrations（至少 0014_asset_duration）。
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

COMMIT;

-- 验证：两项查询都必须至少返回一行。
SELECT product, version, credits_per_minute, created_at
FROM product_prices
WHERE product = 'short_drama_narration'
ORDER BY version DESC;

SELECT id, template_name, version, definition, created_at
FROM workflow_template_snapshots
WHERE template_name = 'short_drama_narration'
ORDER BY created_at DESC;

-- 用户余额不应在此处通过 SQL 直接改写：新注册用户会自动获得 100 创作点，
-- 运营充值请使用 `python -m narrato_api.cli credits grant`，以同时写入 credit_accounts 与 credit_ledger。
