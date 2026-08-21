# 管理后台 API（`/api/v1/admin`）

管理端与普通用户端完全独立：管理员存储于 `admin_users`，使用 `adm1.*` Bearer
Token，不能用于用户端接口。除 `POST /auth/login` 外，所有接口要求：

```http
Authorization: Bearer <admin-token>
```

所有响应均为 `{ code, message, data, request_id }`。列表 `GET` 支持 `page`
和 `page_size`（最大 1000）；使用 `page_size=1000` 后由前端按当前已加载的字段与
筛选条件导出，无独立导出接口。

## 首次部署

1. 执行 `alembic upgrade head`，迁移创建预置权限、菜单和 `super_admin` 角色。
2. 在仅服务可读的私有 TOML 设置 `admin_session_hmac_secret`（至少 32 字节）和
   `admin_bootstrap_password`（至少 8 字节且包含字母、数字）。
3. 启动 Web 服务；数据库尚无管理员时，服务仅创建一次 `Admin` 超级管理员并赋予
   `super_admin` 角色。后续修改 bootstrap 配置不会改写任何账户。

`api_key` 与标记为 `is_secret` 的系统配置永不在读取接口或审计日志中返回明文。

独立部署的前端须将私有配置中的 `admin_cors_origins` 设置为其精确 Origin（逗号分隔）；默认空值不发送跨域许可。仅允许 `GET`、`POST`、`PATCH`、`OPTIONS` 和 `Authorization`、`Content-Type`、`X-Request-ID` 请求头，不使用通配 Origin 或凭据。

## 接口与权限

| 模块 | 端点 | 权限 |
| --- | --- | --- |
| 认证 | `POST /auth/login`、`GET /auth/me`、`POST /auth/logout` | 登录公开；其余已认证 |
| 运营总览 | `GET /overview` | `admin:overview:read` |
| 用户 | `GET /users`、`GET /users/{id}` | `admin:users:read` |
| 用户状态 | `PATCH /users/{id}/status`、`PATCH /users/batch-status` | `admin:users:manage` |
| 任务 | `GET /tasks`、`GET /tasks/{id}` | `admin:tasks:read` |
| 模型/玩法/供应商 | `GET /models|/play-modes|/providers` | `admin:models:read` |
| 模型/玩法/供应商修改 | `PATCH /models/{id}`、`PATCH /play-modes/{id}`、`PATCH /providers/{id}` | `admin:models:manage` |
| 系统配置 | `GET /system-configs`、`PATCH /system-configs/{key}` | `admin:configs:read/manage` |
| 日志 | `GET /credit-ledger`、`GET /operation-logs` | `admin:logs:read` |
| RBAC | `GET|POST /admins`、`PATCH /admins/{id}` | `admin:rbac:read/manage` |
| RBAC | `GET|POST /roles`、`PATCH /roles/{id}` | `admin:rbac:read/manage` |
| RBAC | `GET|POST|PATCH /permissions` | `admin:rbac:read/manage` |
| 菜单 | `GET|POST|PATCH /menus`、`GET /menus/tree` | `admin:rbac:read/manage` |

`GET /overview` 返回用户总量/活跃量、模型任务与工作流总量、按状态聚合、当日模型任务
趋势、当日积分流水聚合与最近 10 条模型任务。写操作写入 `admin_operation_logs`，记录
管理员、请求 ID、IP、对象、脱敏前后值和结果。
