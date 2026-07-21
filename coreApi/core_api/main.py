from __future__ import annotations

import re
import secrets
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from core_api.api.errors import ApiError
from core_api.api.dependencies import BoundedReadinessExecutor
from core_api.api.responses import envelope
from core_api.api.router import api_router
from core_api.config import Settings, load_settings
from core_api.logging import configure_logging

_REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")


def _request_id(request: Request) -> str:
    """返回中间件已确认的请求 ID。"""

    return getattr(request.state, "request_id", f"req_{secrets.token_urlsafe(18)}")


def _error_response(
    request: Request,
    *,
    status_code: int,
    code: str,
    message: str,
    data: object | None = None,
) -> JSONResponse:
    """构建带请求 ID Header 的错误响应。"""

    request_id = _request_id(request)
    return JSONResponse(
        status_code=status_code,
        content=envelope(
            request_id=request_id,
            code=code,
            message=message,
            data=data,
        ),
        headers={"X-Request-ID": request_id},
    )


def create_app(settings: Settings | None = None) -> FastAPI:
    """创建注册统一协议和 `/api/v1` 路由的 Core 应用。"""

    current = settings or load_settings()
    configure_logging(current)
    readiness_executor = BoundedReadinessExecutor(max_workers=2)

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        """在应用关闭时释放私有 readiness 线程资源。"""

        try:
            yield
        finally:
            readiness_executor.close()

    app = FastAPI(title="Narrato Core API", version="1.0.0", lifespan=lifespan)
    app.state.settings = current
    app.state.oss_readiness_executor = readiness_executor

    @app.middleware("http")
    async def attach_request_id(request: Request, call_next):
        """校验或生成请求 ID，并同步写入响应 Header。"""

        supplied = request.headers.get("X-Request-ID", "")
        request.state.request_id = (
            supplied
            if _REQUEST_ID_PATTERN.fullmatch(supplied)
            else f"req_{secrets.token_urlsafe(18)}"
        )
        response = await call_next(request)
        response.headers["X-Request-ID"] = request.state.request_id
        return response

    @app.exception_handler(ApiError)
    async def handle_api_error(request: Request, error: ApiError) -> JSONResponse:
        """将公开业务异常转换为稳定错误信封。"""

        return _error_response(
            request,
            status_code=error.status_code,
            code=error.code,
            message=error.message,
            data=error.data,
        )

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(
        request: Request, error: RequestValidationError
    ) -> JSONResponse:
        """返回不含请求体和内部对象的字段校验错误。"""

        details = [
            {"loc": list(item["loc"]), "type": item["type"]} for item in error.errors()
        ]
        return _error_response(
            request,
            status_code=422,
            code="VALIDATION_ERROR",
            message="请求参数校验失败",
            data={"errors": details},
        )

    @app.exception_handler(StarletteHTTPException)
    async def handle_http_error(
        request: Request, error: StarletteHTTPException
    ) -> JSONResponse:
        """统一框架级 404 与方法错误。"""

        code = "NOT_FOUND" if error.status_code == 404 else "HTTP_ERROR"
        message = "资源不存在" if error.status_code == 404 else "请求无法处理"
        return _error_response(
            request,
            status_code=error.status_code,
            code=code,
            message=message,
        )

    @app.exception_handler(Exception)
    async def handle_unexpected_error(
        request: Request, error: Exception
    ) -> JSONResponse:
        """隐藏未预期异常的堆栈、路径和敏感上下文。"""

        return _error_response(
            request,
            status_code=500,
            code="INTERNAL_ERROR",
            message="服务内部错误",
        )

    app.include_router(api_router, prefix="/api/v1")
    return app


app = create_app()
