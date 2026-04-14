"""LogoGenerator — 이미지 클라이언트를 주입받아 로고 bytes 를 반환한다.

`ImageClientProtocol` 을 따르는 어떤 구현체든 넣을 수 있음 (FakeImageClient,
OpenAIImageClient 등).  프롬프트 조립은 prompts.py 의 순수 함수에 위임.
"""

from __future__ import annotations

from typing import Protocol

from logo_gen_exp.prompts import build_logo_generation_prompt

DEFAULT_SIZE = "1024x1024"


class ImageClientProtocol(Protocol):
    """로고 생성·편집에 필요한 최소 인터페이스."""

    def generate_png(self, *, prompt: str, size: str) -> bytes: ...

    def edit_png(self, *, image: bytes, prompt: str, size: str) -> bytes: ...


class LogoGenerator:
    """브랜드 이름+색상 → 로고 PNG 바이트.

    의존성 주입을 통해 실제 OpenAI 호출(`OpenAIImageClient`) 또는
    테스트용 `FakeImageClient` 를 자유롭게 교체.
    """

    def __init__(self, client: ImageClientProtocol, *, size: str = DEFAULT_SIZE) -> None:
        self.client = client
        self.size = size

    def generate(self, *, name: str, color_hex: str) -> bytes:
        prompt = build_logo_generation_prompt(name=name, color_hex=color_hex)
        return self.client.generate_png(prompt=prompt, size=self.size)
