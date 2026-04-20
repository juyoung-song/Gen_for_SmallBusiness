"""토큰 암호화/복호화 유틸리티 (Fernet 대칭키 암호화)."""

from cryptography.fernet import Fernet


def encrypt_token(token: str, key: str) -> str:
    """평문 토큰을 Fernet으로 암호화하여 반환."""
    f = Fernet(key.encode())
    return f.encrypt(token.encode()).decode()


def decrypt_token(encrypted: str, key: str) -> str:
    """암호화된 토큰을 Fernet으로 복호화하여 반환."""
    f = Fernet(key.encode())
    return f.decrypt(encrypted.encode()).decode()


def generate_fernet_key() -> str:
    """새 Fernet 키 생성 (.env 초기 설정 시 사용)."""
    return Fernet.generate_key().decode()
