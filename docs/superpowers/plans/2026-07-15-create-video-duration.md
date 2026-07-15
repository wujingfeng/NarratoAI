# 创建页视频时长与创作类型限制 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让 `/dashboard/create` 上传视频后自动展示本地时长，并将创作类型数量超限提示延迟到下一步。

**Architecture:** 保持 `CreatePage` 作为页面状态拥有者。新增本地媒体元数据读取函数，通过 object URL 驱动 `setVideos`；创作类型切换仅修改选择状态，下一步回调负责数量校验。现有子组件和视觉结构不变。

**Tech Stack:** React 19、浏览器 HTMLMediaElement API、Vite、Playwright。

## Global Constraints

- 时长读取完全在浏览器本地完成，不发起网络请求。
- 读取失败静默保留 `--:--`。
- 上传时继续执行当前类型的 `maxVideos` 限制。
- 切换类型不因已有视频数量超限而失败。
- 下一步超限时只显示 Toast，不进入参数页面。

---

### Task 1: 实现本地视频时长读取

**Files:**
- Modify: `docs/web/homepage-prototype/src/pages/CreatePage.jsx`
- Test: `docs/web/homepage-prototype/scripts/verify-create.mjs`

**Interfaces:**
- `readVideoDuration(file)`：返回 `Promise<number | null>`，失败或无效元数据返回 `null`。
- `handleVideoFiles(files)`：先加入条目，再异步更新对应条目时长。

- [ ] **Step 1: 增加源码行为断言**

在现有创建页验证脚本中增加源码断言，确认实现包含 `URL.createObjectURL`、`loadedmetadata`、`URL.revokeObjectURL`，并确认真实文件初始值仍为 `durationLabel: "--:--"`。

- [ ] **Step 2: 实现 duration 读取函数**

在 `CreatePage.jsx` 中使用 `document.createElement("video")`，设置 `preload = "metadata"`，监听 `loadedmetadata`、`error`，并在 `settle` 中移除监听与释放 object URL。只有 `Number.isFinite(video.duration) && video.duration >= 0` 时返回四舍五入后的秒数。

- [ ] **Step 3: 接入文件添加流程**

为每个 accepted file 生成稳定 id，加入列表后调用 `readVideoDuration(file)`；成功时使用函数式 `setVideos`，仅更新仍存在且 id 匹配的条目，写入 `durationSeconds` 和 `formatDuration(durationSeconds)`；失败时不修改条目、不显示 Toast。

- [ ] **Step 4: 运行构建和创建页验证**

运行：

```bash
npm run build
npm run verify:create
```

预期：构建成功，现有创建页交互验证通过。

### Task 2: 调整创作类型和下一步校验

**Files:**
- Modify: `docs/web/homepage-prototype/src/pages/CreatePage.jsx`
- Test: `docs/web/homepage-prototype/scripts/verify-create.mjs`

**Interfaces:**
- `handleTypeChange(typeId)`：只切换选中类型，不因数量超限阻止。
- `handleNext()`：超限显示数量 Toast，否则保留原下一步提示。

- [ ] **Step 1: 更新交互验证断言**

在验证脚本中覆盖：已有 3 条演示素材时切换到“视频翻译”成功；点击下一步显示数量限制提示；删除多余素材后点击下一步显示 `参数设置功能建设中`。

- [ ] **Step 2: 修改类型切换逻辑**

移除 `handleTypeChange` 中基于 `videos.length > nextType.maxVideos` 的 Toast 和 `return`，保留 `setSelectedType(typeId)`。

- [ ] **Step 3: 增加下一步数量校验**

新增 `handleNext`：当 `videos.length > selectedCreationType.maxVideos` 时调用 `showUnavailable`，文案包含当前数量、类型名称和上限；否则调用现有参数设置 Toast。将 `CreationSummary` 的 `onNext` 改为 `handleNext`。

- [ ] **Step 4: 运行定向验证**

运行：

```bash
npm run verify:create
```

预期：类型切换、上传限制、下一步提示和删除恢复行为全部通过。

### Task 3: 最终回归与静态检查

**Files:**
- No production files beyond Tasks 1-2.

- [ ] **Step 1: 执行完整验证**

```bash
npm run build
npm run verify:routing
npm run verify:dashboard
npm run verify:create
git diff --check
```

- [ ] **Step 2: 检查范围和禁止贴图规则**

确认改动只涉及创建页逻辑及其验证脚本；搜索 `data:image`、`base64`、`drawImage`、`background-image: url`，预期无新增命中。

- [ ] **Step 3: 复核需求**

逐项确认时长成功展示、失败静默、上传限制保留、类型可切换、下一步超限提示均覆盖；记录无法运行的验证及原因。
