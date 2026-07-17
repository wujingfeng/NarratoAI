from __future__ import annotations

import asyncio
import re
import secrets
import time
import logging
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.responses import Response
from starlette.exceptions import HTTPException as StarletteHTTPException

from narrato_api.api.dependencies import BoundedReadinessExecutor
from narrato_api.api.errors import ApiError
from narrato_api.api.responses import envelope
from narrato_api.api.router import api_router
from narrato_api.config import Settings, load_settings
from narrato_api.database import acquire_database_engine, release_database_engine
from narrato_api.auth.service import AccountLockRegistry
from narrato_api.celery_app import create_celery_app
from narrato_api.integrations.mail_client import CeleryMailDispatcher
from narrato_api.logging import (
    acquire_logging,
    bind_request_id,
    contains_configured_secret,
    configure_logging,
    release_logging,
    reset_request_id,
)

_REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")
_logger = logging.getLogger(__name__)


def _new_request_id() -> str:
    """生成带时间顺序和高熵随机量的请求 ID。"""

    return f"req_{time.time_ns():x}{secrets.token_hex(12)}"


def _request_id(request: Request) -> str:
    """返回中间件已经校验的请求 ID。"""

    return getattr(request.state, "request_id", _new_request_id())


def _error_response(
    request: Request,
    *,
    status_code: int,
    code: str,
    message: str,
    data: object | None = None,
) -> JSONResponse:
    """构建 Header 与正文请求 ID 一致的安全错误响应。"""

    request_id = _request_id(request)
    return JSONResponse(
        status_code=status_code,
        content=envelope(
            request_id=request_id, code=code, message=message, data=data
        ),
        headers={"X-Request-ID": request_id},
    )


def create_app(settings: Settings | None = None) -> FastAPI:
    """创建只暴露 `/api/v1` 业务协议的独立 FastAPI 应用。"""

    current = settings or load_settings()
    configure_logging(current)
    executor = BoundedReadinessExecutor(max_workers=3)

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        """应用退出时释放 readiness 专用线程资源。"""

        logging_lease = acquire_logging(current)
        database_owned = False
        dispatcher_owned = False
        body_error: BaseException | None = None
        try:
            _app.state.database_engine = acquire_database_engine(current)
            database_owned = True
            _app.state.auth_account_locks = AccountLockRegistry()
            _app.state.mail_dispatcher = CeleryMailDispatcher(
                celery=create_celery_app(current),
                sealing_secret=current.verification_code_hmac_secret,
            )
            dispatcher_owned = True
            yield
        except BaseException as error:
            body_error = error
        finally:
            cleanup_errors: list[BaseException] = []

            def remember_cleanup_error(error: BaseException, code: str) -> None:
                """保存清理失败且仅记录不包含异常正文的稳定字段。"""

                cleanup_errors.append(error)
                if isinstance(error, asyncio.CancelledError):
                    return
                _logger.error(
                    "application cleanup failed",
                    extra={
                        "error_type": type(error).__name__,
                        "error_code": code,
                    },
                )

            try:
                await executor.aclose(timeout=current.readiness_timeout_seconds)
            except BaseException as error:
                remember_cleanup_error(error, "EXECUTOR_CLEANUP_FAILED")
            try:
                if dispatcher_owned:
                    _app.state.mail_dispatcher.close()
            except BaseException as error:
                remember_cleanup_error(error, "CELERY_PRODUCER_CLEANUP_FAILED")
            try:
                if database_owned:
                    release_database_engine(current)
            except BaseException as error:
                remember_cleanup_error(error, "DATABASE_CLEANUP_FAILED")
            try:
                release_logging(logging_lease)
            except BaseException as error:
                remember_cleanup_error(error, "LOGGING_CLEANUP_FAILED")

            ordered_errors = (
                ([body_error] if body_error is not None else []) + cleanup_errors
            )
            cancellation = next(
                (
                    error
                    for error in ordered_errors
                    if isinstance(error, asyncio.CancelledError)
                ),
                None,
            )
            if cancellation is not None:
                raise cancellation
            if body_error is not None:
                raise body_error
            if cleanup_errors and not isinstance(cleanup_errors[0], Exception):
                raise cleanup_errors[0]
            if cleanup_errors:
                raise RuntimeError("application cleanup failed") from None

    app = FastAPI(title="Narrato Business API", version="1.0.0", lifespan=lifespan)
    app.state.settings = current
    app.state.readiness_executor = executor

    @app.middleware("http")
    async def attach_request_id(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        """过滤不可信请求 ID 并同步写入响应 Header。"""

        supplied = request.headers.get("X-Request-ID", "")
        request.state.request_id = (
            supplied
            if _REQUEST_ID_PATTERN.fullmatch(supplied)
            and not contains_configured_secret(supplied)
            else _new_request_id()
        )
        token = bind_request_id(request.state.request_id)
        try:
            response = await call_next(request)
            response.headers["X-Request-ID"] = request.state.request_id
            return response
        finally:
            reset_request_id(token)

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
        """返回不包含请求体值和内部对象的字段错误。"""

        details = [
            {"loc": list(item["loc"]), "type": item["type"]}
            for item in error.errors()
        ]
        return _error_response(
            request,
            status_code=422,
            code="VALIDATION_ERROR",
            message="Request validation failed",
            data={"errors": details},
        )

    @app.exception_handler(StarletteHTTPException)
    async def handle_http_error(
        request: Request, error: StarletteHTTPException
    ) -> JSONResponse:
        """统一框架 404、405 和其他 HTTP 错误。"""

        if error.status_code == 404:
            code, message = "NOT_FOUND", "Resource not found"
        elif error.status_code == 405:
            code, message = "METHOD_NOT_ALLOWED", "Method not allowed"
        else:
            code, message = "HTTP_ERROR", "Request could not be processed"
        return _error_response(
            request, status_code=error.status_code, code=code, message=message
        )

    @app.exception_handler(Exception)
    async def handle_unexpected_error(
        request: Request, error: Exception
    ) -> JSONResponse:
        """隐藏未知异常的堆栈、路径、连接和密钥。"""

        _logger.error(
            "unhandled request failure",
            extra={
                "request_id": _request_id(request),
                "error_type": type(error).__name__,
                "error_code": "INTERNAL_ERROR",
            },
        )
        return _error_response(
            request,
            status_code=500,
            code="INTERNAL_ERROR",
            message="Internal service error",
        )

    app.include_router(api_router, prefix="/api/v1")
    return app


app = create_app()
