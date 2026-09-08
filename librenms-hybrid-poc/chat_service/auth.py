"""Verification of short-lived LibreNMS-issued identities."""

from __future__ import annotations

import base64
from dataclasses import dataclass
import hashlib
import hmac
import json
import re
import time
from typing import Callable


class AuthError(ValueError):
    """A deliberately non-specific authentication failure."""


@dataclass(frozen=True)
class Identity:
    sub: str
    name: str
    demo_control: bool = False


_BASE64URL = re.compile(r"^[A-Za-z0-9_-]+$")


def _decode(value: str) -> bytes:
    if not isinstance(value, str) or not _BASE64URL.fullmatch(value):
        raise AuthError("invalid token")
    try:
        return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
    except Exception as exc:
        raise AuthError("invalid token") from exc


class IdentityVerifier:
    def __init__(self, secret: bytes, *, clock: Callable[[], float] = time.time):
        if not isinstance(secret, bytes) or len(secret) != 32:
            raise ValueError("AI assistant shared secret must be exactly 32 bytes")
        self._secret = secret
        self._clock = clock

    def verify(self, value: str) -> Identity:
        if not isinstance(value, str):
            raise AuthError("invalid token")
        pieces = value.split(".")
        if len(pieces) != 3 or pieces[0] != "v1":
            raise AuthError("invalid token")
        encoded, supplied = pieces[1:]
        try:
            payload = json.loads(_decode(encoded).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError, AuthError) as exc:
            raise AuthError("invalid token") from exc
        expected = hmac.new(self._secret, encoded.encode("ascii"), hashlib.sha256).digest()
        if not hmac.compare_digest(expected, _decode(supplied)):
            raise AuthError("invalid token")
        required = ("sub", "name", "iss", "aud", "iat", "exp")
        if not isinstance(payload, dict) or any(key not in payload for key in required):
            raise AuthError("invalid token")
        sub, name, issued, expires = (payload[key] for key in ("sub", "name", "iat", "exp"))
        if (not isinstance(sub, str) or not sub or not isinstance(name, str)
                or isinstance(issued, bool) or not isinstance(issued, int)
                or isinstance(expires, bool) or not isinstance(expires, int)):
            raise AuthError("invalid token")
        if payload["iss"] != "librenms" or payload["aud"] != "ai-assistant":
            raise AuthError("invalid token")
        if expires != issued + 3600:
            raise AuthError("invalid token")
        now = self._clock()
        if issued > now + 30 or expires <= now:
            raise AuthError("invalid token")
        return Identity(
            sub=sub,
            name=name,
            demo_control=payload.get("demo_control") is True,
        )
