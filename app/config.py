import os

# Required settings fail at import, so a misconfigured container never starts serving.
WEBHOOK_SECRET = os.environ["WEBHOOK_SECRET"].encode()
if not WEBHOOK_SECRET:
    raise RuntimeError("WEBHOOK_SECRET is empty: every signature would be computable without a secret")
DATABASE_URL = os.environ["DATABASE_URL"]

MAX_BODY_BYTES = 64 * 1024
