# APIMart 视频 Provider 配置

`provider_code=apimart` 只用于选择 `ApimartProviderAdapter`。提交域名和轮询域名完全由每条 Provider 配置中的 `submit_url`、`status_query_url` 决定；不得通过域名判断 Provider 或协议。

## 必填配置

| 字段 | 说明 |
| --- | --- |
| `provider_code` | 固定为 `apimart` |
| `request_profile` | 下表中的协议 Profile |
| `provider_model_id` | APIMart 要求的实际模型 ID |
| `submit_url` | 例如 `https://<当前网关域名>/v1/videos/generations` |
| `status_query_url` | 例如 `https://<当前网关域名>/v1/tasks/{task_id}` |
| `status_query_method` | `GET` |
| `api_key` | APIMart Bearer Token |

URL 必须是 HTTPS 且解析到公网地址。Provider 域名迁移时，仅更新上述 URL 配置。

## 请求 Profile

| `request_profile` | 适用模型 | 主要映射 |
| --- | --- | --- |
| `seedance_2x` | Seedance 2.0 / fast / mini、Seedance 2.5 | `size`、`generate_audio`、多模态参考 |
| `seedance_15` | Seedance 1.5 Pro | `aspect_ratio`、`audio`、首尾帧图片 |
| `minimax_h3` | MiniMax-H3 | `aspect_ratio`、首/尾帧与多模态参考互斥 |
| `wan_30` | Wan 3.0 | `size`、`generation_type`、`file_url` / `link_url` |
| `kling_v3` | Kling v3 | `mode`、`negative_prompt`、`multi_shot`、`multi_prompt`、`element_list` |

APIMart 提交响应按 `data[0].task_id` 解析；任务查询按 `data.status` 和 `data.result.videos[0].url[0]` 解析。

## Provider 专有参数

`POST /products/ai-video/tasks` 可以在 `provider_options` 中传入 Profile 白名单字段。字段会随 `model_tasks.provider_options` 冻结，未知字段会被拒绝：

- `seedance_2x`：`seed`、`return_last_frame`
- `seedance_15`：`seed`、`camerafixed`
- `wan_30`：`generation_type`、`file_url`、`link_url`
- `kling_v3`：`mode`、`negative_prompt`、`watermark`、`multi_shot`、`shot_type`、`multi_prompt`、`element_list`

管理后台的 Provider 编辑接口可修改 `request_profile`、模型 ID、URL 与密钥。启用前需同时启用对应模型、玩法、Provider 和价格规则。
