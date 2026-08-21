# 短剧解说手动模式闭环修复 TODO

目标：让手动模式稳定完成“脚本结果 → EditorDraft → EditorRevision → Core Render → Artifact → 结果下载”闭环；所有状态推进由服务端与 Outbox 驱动。

## 修复清单

- [x] **1. 脚本结果落入编辑草稿**：将 Core `script_generation` 的规范化 timeline 转换为编辑器可读取的 `EditorDraft`，禁止空脚本文本草稿进入编辑页。
- [x] **2. 运行时 DAG 对齐**：项目启动时创建分析、脚本生成、人工编辑门、渲染和产物发布节点；不再依赖“仅四个分析节点 + 动态插入渲染节点”。
- [x] **3. 不可变 RenderSnapshot**：提交编辑器时校验并冻结完整素材顺序、时间线、音色与成片参数；Revision 与 Render Outbox 必须可追溯。
- [x] **4. 真实渲染派发**：Business Core Client 与 Orchestrator 支持 `script_generation`、`video_render`，Outbox 使用真实 Core Task ID，不使用伪任务 ID。
- [x] **5. 参数和多视频传递**：RenderSnapshot 使用项目全部视频，并将 BGM、字幕样式、视频比例等配置一路传至 Core Render。
- [x] **6. Artifact 登记与结果收口**：Core 渲染成功时幂等登记视频、字幕、配音、时间线产物；服务端推进 `generate → export`。
- [x] **7. 回归测试**：补充真实手动链路 E2E，覆盖重复回调、渲染失败退款、结果视频下载与多视频顺序。

## 约束

- 旧项目与历史工作流保持只读兼容；新项目使用新的工作流快照。
- 不在前端伪造任务状态，不能以页面跳转替代服务端状态机。
- 任何 Core 调用都在事务外执行；事务内只写入 Revision、节点 Attempt、状态和 Outbox。

## 验证记录（2026-08-03）

- Business：`28 passed`，覆盖脚本草稿转换、DAG/编辑门、真实 Render 派发、回调幂等、失败退款、产物可见性和结果查询。
- Core：`7 passed`，覆盖 Render 请求冻结 `render_config`、渲染任务和短剧分析 fake provider 链路。
- 静态检查：`python -m compileall` 与 `git diff --check` 通过。
