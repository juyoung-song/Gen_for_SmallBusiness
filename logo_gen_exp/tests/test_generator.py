"""LogoGenerator 단위 테스트 — Fake 주입으로 OpenAI 호출 없이 로직만 검증.

TDD 사이클 2 RED → GREEN.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pytest

from logo_gen_exp.generator import LogoGenerator


@dataclass
class FakeImageClient:
    """ImageClientProtocol 최소 충족 테스트 더블."""

    response_bytes: bytes = b"PNG_FAKE_BYTES"
    calls: list[dict[str, Any]] = field(default_factory=list)

    def generate_png(self, *, prompt: str, size: str) -> bytes:
        self.calls.append({"prompt": prompt, "size": size})
        return self.response_bytes


class TestLogoGenerator:
    def test_returns_bytes_from_client(self):
        fake = FakeImageClient(response_bytes=b"PNG_X")
        gen = LogoGenerator(client=fake)
        out = gen.generate(name="goorm", color_hex="#5562EA")
        assert out == b"PNG_X"

    def test_prompt_includes_name_and_color(self):
        fake = FakeImageClient()
        gen = LogoGenerator(client=fake)
        gen.generate(name="구름", color_hex="#FF00AA")
        assert len(fake.calls) == 1
        prompt = fake.calls[0]["prompt"]
        assert '"구름"' in prompt
        assert "#FF00AA" in prompt

    def test_default_size_is_1024_square(self):
        fake = FakeImageClient()
        gen = LogoGenerator(client=fake)
        gen.generate(name="x", color_hex="#000000")
        assert fake.calls[0]["size"] == "1024x1024"

    def test_client_called_exactly_once(self):
        fake = FakeImageClient()
        gen = LogoGenerator(client=fake)
        gen.generate(name="a", color_hex="#000000")
        gen.generate(name="b", color_hex="#111111")
        assert len(fake.calls) == 2
        assert fake.calls[0]["prompt"] != fake.calls[1]["prompt"]
