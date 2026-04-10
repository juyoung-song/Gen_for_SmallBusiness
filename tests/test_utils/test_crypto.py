"""토큰 암복호화 유틸 테스트."""

from __future__ import annotations

import pytest

from utils.crypto import decrypt_token, encrypt_token


class TestCrypto:
    def test_round_trip_encrypts_and_decrypts_token(self):
        encrypted = encrypt_token("secret-token", "my-test-key")

        assert encrypted != "secret-token"
        assert decrypt_token(encrypted, "my-test-key") == "secret-token"

    def test_raises_when_secret_missing(self):
        with pytest.raises(ValueError):
            encrypt_token("secret-token", "")
