import base64
import hashlib
import hmac
import json
import os
import time


def _secret_key() -> str:
    return (
        os.getenv("APP_SECRET")
        or os.getenv("ADMIN_PASSWORD")
        or "change-this-secret-before-production"
    )


def create_token(payload: dict) -> str:
    enriched_payload = dict(payload)
    enriched_payload["exp"] = int(time.time()) + int(os.getenv("AUTH_TOKEN_TTL_SECONDS", "43200"))

    body = base64.urlsafe_b64encode(
        json.dumps(enriched_payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    ).decode("utf-8").rstrip("=")
    signature = hmac.new(
        _secret_key().encode("utf-8"),
        body.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return f"{body}.{signature}"


def decode_token(token: str) -> dict:
    try:
        body, signature = token.split(".", 1)
    except ValueError as exc:
        raise ValueError("Invalid token format") from exc

    expected_signature = hmac.new(
        _secret_key().encode("utf-8"),
        body.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    if not hmac.compare_digest(signature, expected_signature):
        raise ValueError("Invalid token signature")

    padded_body = body + "=" * (-len(body) % 4)
    payload = json.loads(base64.urlsafe_b64decode(padded_body.encode("utf-8")))
    if payload.get("exp", 0) < int(time.time()):
        raise ValueError("Token expired")
    return payload