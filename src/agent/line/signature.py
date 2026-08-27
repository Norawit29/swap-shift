import base64
import hashlib
import hmac


def verify_signature(channel_secret: str, body: bytes, signature: str | None) -> bool:
    if not signature or not channel_secret:
        return False
    digest = hmac.new(channel_secret.encode("utf-8"), body, hashlib.sha256).digest()
    return hmac.compare_digest(base64.b64encode(digest).decode(), signature)
