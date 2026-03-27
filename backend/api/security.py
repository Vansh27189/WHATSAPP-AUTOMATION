from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from datetime import datetime, timezone
from uuid import uuid4

from fastapi import HTTPException

from backend.config import APP_SECRET, AUTH_ACCESS_TTL_SECONDS, AUTH_REFRESH_TTL_SECONDS
from backend.database import is_token_revoked, revoke_token


class TokenPayloadError(ValueError):
    pass


def _serialize(payload: dict) -> str:
    return base64.urlsafe_b64encode(
        json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    ).decode("utf-8").rstrip("=")


def _deserialize(payload: str) -> dict:
    padded_body = payload + "=" * (-len(payload) % 4)
    return json.loads(base64.urlsafe_b64decode(padded_body.encode("utf-8")))


def _sign(body: str) -> str:
    return hmac.new(APP_SECRET.encode("utf-8"), body.encode("utf-8"), hashlib.sha256).hexdigest()


def create_token(payload: dict, token_type: str = "access") -> str:
    ttl = AUTH_REFRESH_TTL_SECONDS if token_type == "refresh" else AUTH_ACCESS_TTL_SECONDS
    enriched_payload = dict(payload)
    enriched_payload.update(
        {
            "type": token_type,
            "jti": uuid4().hex,
            "exp": int(time.time()) + ttl,
        }
    )
    body = _serialize(enriched_payload)
    return f"{body}.{_sign(body)}"


async def decode_token(token: str, expected_type: str | None = None) -> dict:
    try:
        body, signature = token.split(".", 1)
    except ValueError as exc:
        raise TokenPayloadError("Invalid token format") from exc

    if not hmac.compare_digest(signature, _sign(body)):
        raise TokenPayloadError("Invalid token signature")

    payload = _deserialize(body)
    if payload.get("exp", 0) < int(time.time()):
        raise TokenPayloadError("Token expired")
    if expected_type and payload.get("type") != expected_type:
        raise TokenPayloadError("Invalid token type")
    if await is_token_revoked(payload.get("jti", "")):
        raise TokenPayloadError("Token revoked")
    return payload


async def revoke_serialized_token(token: str) -> None:
    try:
        payload = await decode_token(token)
    except TokenPayloadError as exc:
        if str(exc) in {"Token expired", "Token revoked"}:
            return
        raise
    expires_at = datetime.fromtimestamp(payload["exp"], tz=timezone.utc)
    await revoke_token(payload["jti"], expires_at)


async def require_token(token: str, expected_type: str | None = None) -> dict:
    try:
        return await decode_token(token, expected_type=expected_type)
    except TokenPayloadError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
