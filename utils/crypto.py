"""토큰 암복호화 유틸.

Meta OAuth 토큰을 DB에 평문으로 저장하지 않기 위한 최소 보호 계층이다.
"""

from __future__ import annotations

import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken


def _build_fernet(secret: str) -> Fernet:
    if not secret.strip():
        raise ValueError("TOKEN_ENCRYPTION_KEY 가 비어 있습니다.")
    digest = hashlib.sha256(secret.encode("utf-8")).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def encrypt_token(token: str, secret: str) -> str:
    if not token:
        raise ValueError("암호화할 토큰이 비어 있습니다.")
    return _build_fernet(secret).encrypt(token.encode("utf-8")).decode("utf-8")


def decrypt_token(encrypted_token: str, secret: str) -> str:
    if not encrypted_token:
        raise ValueError("복호화할 토큰이 비어 있습니다.")
    try:
        return _build_fernet(secret).decrypt(encrypted_token.encode("utf-8")).decode(
            "utf-8"
        )
    except InvalidToken as exc:
        raise ValueError("저장된 인스타그램 토큰을 복호화할 수 없습니다.") from exc
