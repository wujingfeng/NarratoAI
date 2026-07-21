from __future__ import annotations

import json
import sys
from typing import Any, cast

from narrato_api.integrations.mail_client import MailPurpose, SmtpMailClient


def main() -> int:
    """从 stdin 接收一次性 SMTP 请求；argv、stdout、stderr 均不含敏感值。"""

    raw = sys.stdin.buffer.read(16_384)
    payload = cast(dict[str, Any], json.loads(raw))
    client = SmtpMailClient(
        host=str(payload["host"]),
        port=int(payload["port"]),
        username=str(payload["username"]),
        password=str(payload["password"]),
        sender=str(payload["sender"]),
        timeout_seconds=float(payload["socket_timeout_seconds"]),
        use_starttls=bool(payload["use_starttls"]),
    )
    client.send_verification_code(
        str(payload["email"]),
        str(payload["verification_code"]),
        purpose=cast(MailPurpose, payload["purpose"]),
        validity_minutes=int(payload["validity_minutes"]),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
