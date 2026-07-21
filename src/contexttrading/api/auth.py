"""API-key authentication (service-level, not multi-user IAM).

Guard logic:

- ``auth_enabled: false`` OR ``allow_anonymous: true`` -> open (local dev).
- Otherwise the ``X-API-Key`` header must match one of the configured
  keys, compared in constant time (``hmac.compare_digest``).
- Failures raise :class:`AuthenticationError` (CT-7001) -> 401 envelope.
"""

from __future__ import annotations

import hmac

from fastapi import Request

from contexttrading.core.config import Settings
from contexttrading.core.errors import AuthenticationError


def require_api_key(request: Request) -> None:
    """FastAPI dependency enforcing the API-key policy."""
    settings: Settings = request.app.state.settings
    config = settings.api
    if not config.auth_enabled or config.allow_anonymous:
        return
    presented = request.headers.get(config.api_key_header, "")
    for valid in config.api_keys:
        if presented and hmac.compare_digest(presented, valid):
            return
    raise AuthenticationError(
        "Missing or invalid API key",
        context={"header": config.api_key_header},
    )
