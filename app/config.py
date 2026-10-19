import os

# Required settings fail at import, so a misconfigured container never starts serving.
WEBHOOK_SECRET = os.environ["WEBHOOK_SECRET"].encode()
DATABASE_URL = os.environ["DATABASE_URL"]

MAX_BODY_BYTES = 64 * 1024
