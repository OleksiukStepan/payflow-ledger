import hashlib
import hmac

from app.config import WEBHOOK_SECRET


def is_valid_signature(body: bytes, signature: str | None) -> bool:
    if not signature:
        return False
    expected = hmac.new(WEBHOOK_SECRET, body, hashlib.sha256).hexdigest().encode()
    # Bytes, not str: compare_digest raises TypeError on non-ASCII strings, and a header can carry any byte.
    return hmac.compare_digest(expected, signature.encode())
