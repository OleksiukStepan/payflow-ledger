import hashlib
import hmac

from app.config import WEBHOOK_SECRETS


def is_valid_signature(body: bytes, signature: str | None) -> bool:
    if not signature:
        return False
    # Bytes, not str: compare_digest raises TypeError on non-ASCII strings, and a header can carry any byte.
    received = signature.encode()
    # Check every configured secret, so the time taken does not reveal which one matched.
    matches = [
        hmac.compare_digest(hmac.new(secret, body, hashlib.sha256).hexdigest().encode(), received)
        for secret in WEBHOOK_SECRETS
    ]
    return any(matches)
