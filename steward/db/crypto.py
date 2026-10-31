"""Master key, value encryption, and token hashing."""

import base64
import hashlib
import hmac

from cryptography.fernet import Fernet

from steward.settings import get_settings


def encrypt(plaintext: str) -> bytes:
    """Ciphertext for a secret value."""
    return _fernet().encrypt(plaintext.encode())


def decrypt(ciphertext: bytes) -> str:
    """Plaintext from ciphertext produced by encrypt."""
    return _fernet().decrypt(bytes(ciphertext)).decode()


def hash_token(token: str) -> str:
    """HMAC of the token. The plaintext token cannot be recovered from it."""
    digest = hmac.new(_master_key(), b"steward-token-v1\0" + token.encode(), hashlib.sha256)
    return digest.hexdigest()


def _master_key() -> bytes:
    return get_settings().master_key_bytes()


def _fernet() -> Fernet:
    digest = hashlib.sha256(b"steward-fernet-v1\0" + _master_key()).digest()
    return Fernet(base64.urlsafe_b64encode(digest))
