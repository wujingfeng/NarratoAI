from __future__ import annotations

from pydantic import field_validator

from narrato_api.api.responses import StrictModel
from narrato_api.auth.service import normalize_email, validate_password


class EmailRequest(StrictModel):
    """验证码发送请求。"""

    email: str

    @field_validator("email")
    @classmethod
    def normalize_email_field(cls, value: str) -> str:
        """规范化并校验邮箱。"""

        return normalize_email(value)


class RegisterRequest(EmailRequest):
    """邮箱验证码注册请求。"""

    password: str
    verification_code: str

    @field_validator("password")
    @classmethod
    def validate_password_field(cls, value: str) -> str:
        """校验注册密码强度与长度。"""

        validate_password(value)
        return value

    @field_validator("verification_code")
    @classmethod
    def validate_code(cls, value: str) -> str:
        """只接受固定六位数字验证码。"""

        if len(value) != 6 or not value.isascii() or not value.isdigit():
            raise ValueError("invalid verification code")
        return value


class LoginRequest(EmailRequest):
    """邮箱密码登录请求。"""

    password: str

    @field_validator("password")
    @classmethod
    def bound_password(cls, value: str) -> str:
        """限制密码输入大小，避免哈希拒绝服务。"""

        if not value or len(value.encode("utf-8")) > 256:
            raise ValueError("invalid password length")
        return value


class PasswordResetRequest(EmailRequest):
    """验证码重置密码请求。"""

    new_password: str
    verification_code: str

    @field_validator("new_password")
    @classmethod
    def validate_new_password(cls, value: str) -> str:
        """校验新密码强度。"""

        validate_password(value)
        return value

    @field_validator("verification_code")
    @classmethod
    def validate_reset_code(cls, value: str) -> str:
        """只接受固定六位数字找回码。"""

        if len(value) != 6 or not value.isascii() or not value.isdigit():
            raise ValueError("invalid verification code")
        return value


class EmptyData(StrictModel):
    """无额外字段的成功结果。"""


class AcceptedData(StrictModel):
    """异步请求已接受结果。"""

    accepted: bool


class UserData(StrictModel):
    """可公开的账户基础字段。"""

    id: str
    email: str
    status: str


class CurrentUserData(UserData):
    """当前账户页可读取的实时资产摘要。"""

    credit_balance: int


class LoginData(StrictModel):
    """仅登录响应返回一次的原始会话 Token。"""

    token: str
    token_type: str = "Bearer"
    expires_in: int
    user: UserData
