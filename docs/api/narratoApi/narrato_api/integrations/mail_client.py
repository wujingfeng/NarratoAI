from __future__ import annotations

import smtplib
import base64
import hashlib
import hmac
import math
import secrets
import threading
from dataclasses import dataclass
from email.message import EmailMessage
from typing import Literal, Protocol

from celery import Celery

MailPurpose = Literal["register", "password_reset"]


class MailClient(Protocol):
    """Worker 内实际发送验证码邮件的最小协议。"""

    def send_verification_code(
        self,
        email: str,
        verification_code: str,
        *,
        purpose: MailPurpose,
        validity_minutes: int,
    ) -> None: ...


class MailDispatcher(Protocol):
    """认证服务触发验证码投递的协议。"""

    def enqueue(
        self,
        email: str,
        verification_code: str,
        *,
        purpose: MailPurpose,
        generation: str,
        deliver: bool,
        ttl_seconds: int,
    ) -> None: ...


class SmtpMailClient:
    """使用 STARTTLS 或隐式 TLS 和有界超时发送验证码邮件。"""

    def __init__(
        self,
        *,
        host: str,
        port: int,
        username: str,
        password: str,
        sender: str,
        timeout_seconds: float,
        use_starttls: bool,
        use_ssl: bool,
    ) -> None:
        """绑定经配置校验的 SMTP 参数。"""

        for value in (host, username, sender):
            if "\r" in value or "\n" in value:
                raise ValueError("SMTP header injection rejected")
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.sender = sender
        self.timeout_seconds = timeout_seconds
        self.use_starttls = use_starttls
        self.use_ssl = use_ssl

    def send_verification_code(
        self,
        email: str,
        verification_code: str,
        *,
        purpose: MailPurpose,
        validity_minutes: int,
    ) -> None:
        """发送不写日志的纯文本验证码邮件。"""

        if any(char in email for char in "\r\n"):
            raise ValueError("SMTP header injection rejected")
        subject = (
            "NarratoAI 注册验证码"
            if purpose == "register"
            else "NarratoAI 密码重置验证码"
        )
        message = EmailMessage()
        message["From"] = self.sender
        message["To"] = email
        message["Subject"] = subject
        message.set_content(
            f"验证码：{verification_code}。{validity_minutes} 分钟内有效，请勿转发。"
        )
        smtp_factory = smtplib.SMTP_SSL if self.use_ssl else smtplib.SMTP
        with smtp_factory(self.host, self.port, timeout=self.timeout_seconds) as client:
            client.ehlo()
            if self.use_starttls:
                client.starttls()
                client.ehlo()
            if self.username:
                client.login(self.username, self.password)
            client.send_message(message)


class SynchronousMailDispatcher:
    """在当前 API 请求内完成验证码 SMTP 发送。"""

    def __init__(self, *, client: MailClient, ttl_seconds: int) -> None:
        """绑定 SMTP 客户端并预先换算验证码有效分钟数。"""

        if ttl_seconds <= 0:
            raise ValueError("verification code TTL must be positive")
        self._client = client
        self._validity_minutes = math.ceil(ttl_seconds / 60)

    def enqueue(
        self,
        email: str,
        verification_code: str,
        *,
        purpose: MailPurpose,
        generation: str,
        deliver: bool,
        ttl_seconds: int,
    ) -> None:
        """保留服务层接口，并在返回前同步完成真实投递。"""

        del generation, ttl_seconds
        if deliver:
            self._client.send_verification_code(
                email,
                verification_code,
                purpose=purpose,
                validity_minutes=self._validity_minutes,
            )


class CeleryMailDispatcher:
    """仅在 Celery Broker 接受任务后向 API 返回成功。"""

    TASK_NAME = "narrato.auth.send_verification_email"

    def __init__(self, *, celery: Celery, sealing_secret: str) -> None:
        """绑定仅 Web 与邮件 Worker 持有的队列载荷保护密钥。"""

        self._celery = celery
        self._sealing_secret = sealing_secret

    def enqueue(
        self,
        email: str,
        verification_code: str,
        *,
        purpose: MailPurpose,
        generation: str,
        deliver: bool,
        ttl_seconds: int,
    ) -> None:
        """通过实例持有的配置化 producer 按固定任务名投递。"""

        sealed_code = seal_verification_code(
            verification_code,
            email=email,
            purpose=purpose,
            secret=self._sealing_secret,
            deliver=deliver,
        )
        self._celery.send_task(
            self.TASK_NAME,
            kwargs={
                "email": email,
                "sealed_code": sealed_code,
                "purpose": purpose,
                "generation": generation,
            },
            expires=ttl_seconds,
        )

    def close(self) -> None:
        """释放当前 FastAPI app 私有 producer 连接池。"""

        self._celery.close()


def seal_verification_code(
    code: str,
    *,
    email: str,
    purpose: MailPurpose,
    secret: str,
    deliver: bool = True,
) -> str:
    """用随机 nonce、HMAC 派生流和认证标签保护 Broker 中的验证码。"""

    nonce = secrets.token_bytes(16)
    key = secret.encode()
    context = f"{purpose}:{email}".encode()
    stream = hmac.new(key, b"enc\0" + nonce + context, hashlib.sha256).digest()
    plaintext = (("1" if deliver else "0") + code).encode("ascii")
    ciphertext = bytes(left ^ right for left, right in zip(plaintext, stream))
    tag = hmac.new(
        key, b"tag\0" + nonce + context + ciphertext, hashlib.sha256
    ).digest()[:16]
    return base64.urlsafe_b64encode(nonce + ciphertext + tag).decode("ascii")


def unseal_verification_code(
    sealed: str, *, email: str, purpose: MailPurpose, secret: str
) -> tuple[str, bool]:
    """验证 Broker 载荷完整性后恢复六位验证码。"""

    try:
        payload = base64.urlsafe_b64decode(sealed.encode("ascii"))
    except (ValueError, UnicodeError) as error:
        raise ValueError("invalid sealed verification code") from error
    if len(payload) != 39:
        raise ValueError("invalid sealed verification code")
    nonce, ciphertext, supplied_tag = payload[:16], payload[16:23], payload[23:]
    key = secret.encode()
    context = f"{purpose}:{email}".encode()
    expected_tag = hmac.new(
        key, b"tag\0" + nonce + context + ciphertext, hashlib.sha256
    ).digest()[:16]
    if not hmac.compare_digest(supplied_tag, expected_tag):
        raise ValueError("invalid sealed verification code")
    stream = hmac.new(key, b"enc\0" + nonce + context, hashlib.sha256).digest()
    plaintext = bytes(left ^ right for left, right in zip(ciphertext, stream)).decode(
        "ascii"
    )
    deliver_flag, code = plaintext[:1], plaintext[1:]
    if deliver_flag not in {"0", "1"} or len(code) != 6 or not code.isdigit():
        raise ValueError("invalid sealed verification code")
    return code, deliver_flag == "1"


@dataclass(frozen=True, slots=True)
class FakeMailMessage:
    """Fake 队列记录，供测试从真实发送边界读取验证码。"""

    email: str
    verification_code: str
    purpose: MailPurpose


class FakeMailDispatcher:
    """不联网且真实保存 enqueue 事实的测试邮件队列。"""

    def __init__(self) -> None:
        self.messages: list[FakeMailMessage] = []
        self.cover_dispatches = 0
        self._lock = threading.Lock()

    def enqueue(
        self,
        email: str,
        verification_code: str,
        *,
        purpose: MailPurpose,
        generation: str,
        deliver: bool,
        ttl_seconds: int,
    ) -> None:
        """记录已接受邮件，不伪报 SMTP 发送成功。"""

        with self._lock:
            del generation, ttl_seconds
            if deliver:
                self.messages.append(FakeMailMessage(email, verification_code, purpose))
            else:
                self.cover_dispatches += 1
