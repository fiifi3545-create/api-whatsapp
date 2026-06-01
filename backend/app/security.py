from __future__ import annotations

import hashlib
import hmac


def verify_meta_signature(app_secret: str, raw_body: bytes, signature_header: str | None) -> bool:
    """Verify Meta's X-Hub-Signature-256 header against the raw request body.

    Returns True when:
      - app_secret is empty (signature check disabled — dev only), OR
      - the header is present, well-formed, and the HMAC matches in constant time.
    """
    if not app_secret:
        return True

    if not signature_header or not signature_header.startswith("sha256="):
        return False

    expected = hmac.new(
        app_secret.encode("utf-8"),
        raw_body,
        hashlib.sha256,
    ).hexdigest()

    received = signature_header.split("=", 1)[1]
    return hmac.compare_digest(expected, received)
