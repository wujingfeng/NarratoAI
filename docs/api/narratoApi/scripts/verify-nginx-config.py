#!/usr/bin/env python3
"""Statically validate the repository's Nginx deployment example.

The check deliberately reads text only: it neither starts Nginx nor writes to
system configuration directories.  ``nginx -t`` remains the syntax check when
the binary is available on the deployment host.
"""

from __future__ import annotations

import sys
from pathlib import Path


SERVICE_ROOT = Path(__file__).resolve().parents[1]
NGINX_CONFIG = SERVICE_ROOT / "deploy" / "nginx.conf"


def _require(config: str, fragment: str, label: str) -> None:
    if fragment not in config:
        raise ValueError(f"missing {label}: {fragment!r}")


def main() -> int:
    """Verify the safety-critical reverse-proxy directives without Nginx."""

    try:
        config = NGINX_CONFIG.read_text(encoding="utf-8")
        required = (
            ("upstream narrato_business_api", "Business API upstream"),
            ("127.0.0.1:8001", "Business API loopback target"),
            ("upstream narrato_core_api", "Core API upstream"),
            ("127.0.0.1:8002", "Core API loopback target"),
            ("location /api/v1/", "Business API location"),
            ("location /core-api/", "Core API location"),
            ("proxy_buffering off", "SSE buffering disable"),
            ("proxy_request_buffering off", "streaming request buffering disable"),
            ("client_max_body_size", "request body limit"),
            ("Access-Control-Allow-Origin", "Web Origin CORS header"),
            ("$cors_origin", "allowlisted Web Origin variable"),
            ("proxy_connect_timeout", "upstream connection timeout"),
            ("proxy_read_timeout", "upstream read timeout"),
            ("limit_req_zone", "request rate-limit zone"),
            ("limit_req zone=", "request rate-limit enforcement"),
            ("limit_conn_zone", "connection-limit zone"),
            ("limit_conn ", "connection-limit enforcement"),
            ("OSS/CDN CORS policy example", "OSS/CDN CORS example"),
            ("AllowedMethod: GET, HEAD", "OSS/CDN GET and HEAD methods"),
            ("AllowedHeader: Range", "OSS/CDN Range header"),
        )
        for fragment, label in required:
            _require(config, fragment, label)
    except (OSError, ValueError) as error:
        print(f"Nginx configuration invalid: {error}", file=sys.stderr)
        return 1

    print("Nginx configuration static checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
