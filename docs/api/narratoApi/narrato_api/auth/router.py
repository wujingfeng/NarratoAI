from __future__ import annotations

from collections.abc import Iterator
from functools import lru_cache
from typing import Annotated

from fastapi import APIRouter, Depends, Header, Request, status
from redis import Redis
from sqlalchemy.orm import Session, sessionmaker

from narrato_api.api.dependencies import get_request_id, get_settings
from narrato_api.api.errors import ApiError
from narrato_api.api.responses import ApiResponse
from narrato_api.auth.redis_store import RedisEmailCodeStore, RedisSessionStore
from narrato_api.auth.schemas import (
    AcceptedData,
    CurrentUserData,
    EmailRequest,
    EmptyData,
    LoginData,
    LoginRequest,
    PasswordResetRequest,
    RegisterRequest,
    UserData,
)
from narrato_api.billing.models import CreditAccount
from narrato_api.auth.service import (
    AuthService,
    EmailCodeManager,
    PasswordHasher,
    SingleSessionTokens,
    authentication_required,
)
from narrato_api.config import Settings

router = APIRouter()


@lru_cache(maxsize=16)
def _password_hasher(
    time_cost: int, memory_cost_kib: int, parallelism: int
) -> PasswordHasher:
    """按安全参数复用昂贵的 Argon2id dummy hash。"""

    return PasswordHasher(
        time_cost=time_cost,
        memory_cost_kib=memory_cost_kib,
        parallelism=parallelism,
    )


def _user_data(user: object) -> UserData:
    """只映射允许公开的账户字段。"""

    return UserData(
        id=str(getattr(user, "id")),
        email=str(getattr(user, "email")),
        status=str(getattr(user, "status")),
    )


def _current_user_data(user: object, *, credit_balance: int) -> CurrentUserData:
    """仅为当前登录用户补充账本驱动的实时余额。"""

    return CurrentUserData(
        id=str(getattr(user, "id")),
        email=str(getattr(user, "email")),
        status=str(getattr(user, "status")),
        credit_balance=credit_balance,
    )


def get_auth_service(
    request: Request, settings: Annotated[Settings, Depends(get_settings)]
) -> Iterator[AuthService]:
    """创建请求作用域数据库会话工厂和同步 Redis 认证适配器。"""

    if not settings.verification_code_hmac_secret:
        raise ApiError(
            "AUTH_SERVICE_UNAVAILABLE", "Authentication service unavailable", 503
        )
    client = Redis.from_url(
        settings.redis_url,
        socket_connect_timeout=settings.auth_redis_timeout_seconds,
        socket_timeout=settings.auth_redis_timeout_seconds,
        retry_on_timeout=False,
    )
    engine = request.app.state.database_engine
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    try:
        yield AuthService(
            session_factory=factory,
            password_hasher=_password_hasher(
                settings.password_argon2_time_cost,
                settings.password_argon2_memory_cost_kib,
                settings.password_argon2_parallelism,
            ),
            codes=EmailCodeManager(
                RedisEmailCodeStore(client, prefix=settings.redis_key_prefix),
                secret=settings.verification_code_hmac_secret,
                ttl_seconds=settings.verification_code_ttl_seconds,
            ),
            tokens=SingleSessionTokens(
                RedisSessionStore(client, prefix=settings.redis_key_prefix),
                ttl_seconds=settings.session_ttl_seconds,
            ),
            mail_dispatcher=request.app.state.mail_dispatcher,
            account_locks=request.app.state.auth_account_locks,
        )
    finally:
        client.close()


def bearer_token(authorization: Annotated[str | None, Header()] = None) -> str:
    """集中解析严格 Bearer Header，所有失败统一为 401。"""

    if authorization is None:
        raise authentication_required()
    scheme, separator, token = authorization.partition(" ")
    if separator != " " or scheme.lower() != "bearer" or not token or " " in token:
        raise authentication_required()
    return token


@router.post(
    "/auth/register-code/send",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=ApiResponse[AcceptedData],
)
def send_register_code(
    body: EmailRequest,
    service: Annotated[AuthService, Depends(get_auth_service)],
    request_id: Annotated[str, Depends(get_request_id)],
) -> ApiResponse[AcceptedData]:
    """同步发送注册验证码。"""

    service.send_register_code(body.email)
    return ApiResponse(
        code="VERIFICATION_CODE_ACCEPTED",
        message="Verification email accepted",
        data=AcceptedData(accepted=True),
        request_id=request_id,
    )


@router.post(
    "/auth/register",
    status_code=status.HTTP_201_CREATED,
    response_model=ApiResponse[UserData],
)
def register(
    body: RegisterRequest,
    service: Annotated[AuthService, Depends(get_auth_service)],
    request_id: Annotated[str, Depends(get_request_id)],
) -> ApiResponse[UserData]:
    """使用一次性验证码创建个人账户。"""

    user = service.register(body.email, body.password, body.verification_code)
    return ApiResponse(
        code="USER_REGISTERED",
        message="User registered",
        data=_user_data(user),
        request_id=request_id,
    )


@router.post("/auth/login", response_model=ApiResponse[LoginData])
def login(
    body: LoginRequest,
    service: Annotated[AuthService, Depends(get_auth_service)],
    settings: Annotated[Settings, Depends(get_settings)],
    request_id: Annotated[str, Depends(get_request_id)],
) -> ApiResponse[LoginData]:
    """验证邮箱密码并原子替换旧会话。"""

    result = service.login(body.email, body.password)
    return ApiResponse(
        code="LOGIN_SUCCEEDED",
        message="Login succeeded",
        data=LoginData(
            token=result.token,
            expires_in=settings.session_ttl_seconds,
            user=_user_data(result.user),
        ),
        request_id=request_id,
    )


@router.post("/auth/logout", response_model=ApiResponse[EmptyData])
def logout(
    token: Annotated[str, Depends(bearer_token)],
    service: Annotated[AuthService, Depends(get_auth_service)],
    request_id: Annotated[str, Depends(get_request_id)],
) -> ApiResponse[EmptyData]:
    """撤销调用方当前会话。"""

    service.resolve_user(token)
    service.logout(token)
    return ApiResponse(
        code="LOGOUT_SUCCEEDED",
        message="Logout succeeded",
        data=EmptyData(),
        request_id=request_id,
    )


@router.post(
    "/auth/password-code/send",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=ApiResponse[AcceptedData],
)
def send_password_code(
    body: EmailRequest,
    service: Annotated[AuthService, Depends(get_auth_service)],
    request_id: Annotated[str, Depends(get_request_id)],
) -> ApiResponse[AcceptedData]:
    """以不可枚举响应同步发送找回密码验证码。"""

    service.send_password_reset_code(body.email)
    return ApiResponse(
        code="VERIFICATION_CODE_ACCEPTED",
        message="Verification email accepted",
        data=AcceptedData(accepted=True),
        request_id=request_id,
    )


@router.post("/auth/password/reset", response_model=ApiResponse[EmptyData])
def reset_password(
    body: PasswordResetRequest,
    service: Annotated[AuthService, Depends(get_auth_service)],
    request_id: Annotated[str, Depends(get_request_id)],
) -> ApiResponse[EmptyData]:
    """使用一次性找回码修改密码并撤销会话。"""

    service.reset_password(body.email, body.verification_code, body.new_password)
    return ApiResponse(
        code="PASSWORD_RESET",
        message="Password reset",
        data=EmptyData(),
        request_id=request_id,
    )


@router.get("/users/me", response_model=ApiResponse[CurrentUserData])
def current_user(
    request: Request,
    token: Annotated[str, Depends(bearer_token)],
    service: Annotated[AuthService, Depends(get_auth_service)],
    request_id: Annotated[str, Depends(get_request_id)],
) -> ApiResponse[CurrentUserData]:
    """返回当前有效且启用的个人账户。"""

    user = service.resolve_user(token)
    with Session(request.app.state.database_engine) as session:
        credit_account = session.get(CreditAccount, user.id)
    if credit_account is None:
        raise ApiError(
            "CREDIT_ACCOUNT_UNAVAILABLE", "Credit account unavailable", 503
        )
    return ApiResponse(
        code="CURRENT_USER",
        message="Current user",
        data=_current_user_data(user, credit_balance=credit_account.balance),
        request_id=request_id,
    )
