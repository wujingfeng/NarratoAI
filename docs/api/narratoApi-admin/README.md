# Narrato API Admin

独立部署的 Narrato API 专业管理后台。前端不保存业务数据，不提供生产 mock；所有页面直接请求 `narratoApi` 管理端 API。

## 技术栈

React 19、Vite、TypeScript、Ant Design、`@ant-design/pro-components`、React Router。

## 启动

```bash
cp .env.example .env.local
npm install
npm run dev # http://127.0.0.1:5280
```

Web 开发/预览服务默认监听 `127.0.0.1:5280`。默认 API 地址是 `http://127.0.0.1:8001/api/v1/admin`，可通过 `VITE_ADMIN_API_BASE_URL` 覆盖。API 响应统一为：

```json
{ "code": "ADMIN_USERS", "message": "ok", "data": {}, "request_id": "req_xxx" }
```

## 后端契约

- 认证：`POST /auth/login`、`GET /auth/me`、`POST /auth/logout`。
- 运营：`GET /overview`。
- 业务列表：`/users`、`/tasks`、`/models`、`/play-modes`、`/providers`、`/system-configs`。
- RBAC：`/admins`、`/roles`、`/permissions`、`/menus`、`/menus/tree`。
- 审计：`/operation-logs`、`/credit-ledger`。

所有请求带 `Authorization: Bearer <admin token>`。列表传 `page`、`page_size`（最大 1000）、`keyword`、`status`、`start_at`、`end_at`；返回 `items,total,page,page_size`。

## 页面能力

- 管理员登录与基于后端返回 `menus` 的树形侧栏；由后端权限控制页面可见性。
- 运营总览真实请求 `/overview`，数据不可用时明确空态，不使用生产 mock。
- 用户详情右侧抽屉、状态启禁；任务按工作流分类；模型/玩法/渠道/系统配置；管理员、角色、权限、菜单；操作日志和积分日志。
- 所有表支持关键字/状态筛选、分页、每页 `10/30/50/100/500/1000`、字段显隐、右侧详情、当前页前端 CSV 导出。导出严格以当前页和当前可见字段为准。

## 校验

```bash
npm run lint
npm run build
```

前端仅负责显示/交互与 Token 传递；管理员初始化、权限校验、写入审计、脱敏和数据库联调由 `narratoApi` 后端完成。模型、玩法、供应商和系统配置的写接口 payload 各不相同，前端在对应表单契约就绪前只读呈现，避免以通用表单写入错误数据。
