import os

# Required settings fail at import, so a misconfigured container never starts serving.
WEBHOOK_SECRET = os.environ["WEBHOOK_SECRET"].encode()
if not WEBHOOK_SECRET:
    raise RuntimeError("WEBHOOK_SECRET is empty: every signature would be computable without a secret")
# Optional: the secret being rotated out, accepted until it is removed from the environment.
WEBHOOK_SECRET_PREVIOUS = os.environ.get("WEBHOOK_SECRET_PREVIOUS", "").encode()
WEBHOOK_SECRETS = tuple(secret for secret in (WEBHOOK_SECRET, WEBHOOK_SECRET_PREVIOUS) if secret)
DATABASE_URL = os.environ["DATABASE_URL"]

MAX_BODY_BYTES = 64 * 1024
