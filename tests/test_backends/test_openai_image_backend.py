"""OpenAIImageBackend 단위 테스트 (Cycle 2 RED→GREEN).

Fake ImageClient 를 주입해 실제 OpenAI 호출 없이 백엔드 로직만 검증.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pytest

from backends.openai_image import DEFAULT_MODEL, DEFAULT_SIZE, OpenAIImageBackend
from schemas.image_schema import ImageGenerationRequest


@dataclass
class _FakeSettings:
    OPENAI_API_KEY: str = "sk-fake"


@dataclass
class _FakeClient:
    """ImageClient 프로토콜 충족."""

    response: bytes = b"\x89PNG_FAKE"
    calls: list[dict[str, Any]] = field(default_factory=list)

    def edit_images(
        self,
        *,
        model: str,
        images: list[tuple[str, bytes]],
        prompt: str,
        size: str,
    ) -> bytes:
        self.calls.append(
            {"model": model, "images": images, "prompt": prompt, "size": size}
        )
        return self.response


def _make_request(
    *, image_data: bytes | None = b"PRODUCT_BYTES", logo_path: str | None = None
) -> ImageGenerationRequest:
    return ImageGenerationRequest(
        product_name="크루아상",
        description="버터 풍미",
        goal="신메뉴 출시",
        style="기본",
        prompt="commercial bakery photo, natural light",  # 번역된 영문
        image_data=image_data,
        brand_prompt="brand prompt",
        is_new_product=True,
        reference_analysis="",
        logo_path=logo_path,
    )


class TestGenerate:
    def test_returns_response_with_bytes(self, tmp_path):
        logo = tmp_path / "logo.png"
        logo.write_bytes(b"LOGO_BYTES")
        fake = _FakeClient(response=b"\x89PNG_RESULT")
        backend = OpenAIImageBackend(_FakeSettings(), client=fake)

        resp = backend.generate(_make_request(logo_path=str(logo)))
        assert resp.image_data == b"\x89PNG_RESULT"
        assert resp.revised_prompt  # 비어있지 않음

    def test_passes_two_images_in_correct_order(self, tmp_path):
        logo = tmp_path / "logo.png"
        logo.write_bytes(b"LOGO_BYTES")
        fake = _FakeClient()
        backend = OpenAIImageBackend(_FakeSettings(), client=fake)

        backend.generate(_make_request(logo_path=str(logo)))
        assert len(fake.calls) == 1
        images = fake.calls[0]["images"]
        # 첫 번째: 상품, 두 번째: 로고
        assert images[0][1] == b"PRODUCT_BYTES"
        assert images[1][1] == b"LOGO_BYTES"
        # 파일명도 다르게 (모델이 어느 게 어느 건지 인지하도록)
        assert images[0][0] != images[1][0]

    def test_prompt_wraps_translated_with_multi_input_guidance(self, tmp_path):
        logo = tmp_path / "logo.png"
        logo.write_bytes(b"LOGO_BYTES")
        fake = _FakeClient()
        backend = OpenAIImageBackend(_FakeSettings(), client=fake)

        backend.generate(_make_request(logo_path=str(logo)))
        sent_prompt = fake.calls[0]["prompt"].lower()
        assert "first image" in sent_prompt
        assert "second image" in sent_prompt
        assert "commercial bakery photo, natural light" in sent_prompt

    def test_uses_default_model_and_size(self, tmp_path):
        logo = tmp_path / "logo.png"
        logo.write_bytes(b"LOGO_BYTES")
        fake = _FakeClient()
        backend = OpenAIImageBackend(_FakeSettings(), client=fake)

        backend.generate(_make_request(logo_path=str(logo)))
        assert fake.calls[0]["model"] == DEFAULT_MODEL
        assert fake.calls[0]["size"] == DEFAULT_SIZE


class TestErrors:
    def test_missing_image_data_raises(self, tmp_path):
        logo = tmp_path / "logo.png"
        logo.write_bytes(b"L")
        backend = OpenAIImageBackend(_FakeSettings(), client=_FakeClient())
        with pytest.raises(RuntimeError, match="상품 사진"):
            backend.generate(_make_request(image_data=None, logo_path=str(logo)))

    def test_missing_logo_path_raises(self):
        backend = OpenAIImageBackend(_FakeSettings(), client=_FakeClient())
        with pytest.raises(RuntimeError, match="logo_path"):
            backend.generate(_make_request(logo_path=None))

    def test_missing_logo_file_raises(self, tmp_path):
        backend = OpenAIImageBackend(_FakeSettings(), client=_FakeClient())
        nonexistent = tmp_path / "nope.png"
        with pytest.raises(FileNotFoundError):
            backend.generate(_make_request(logo_path=str(nonexistent)))


class TestAvailability:
    def test_is_available_with_api_key(self):
        backend = OpenAIImageBackend(_FakeSettings(OPENAI_API_KEY="sk-x"))
        assert backend.is_available()

    def test_is_unavailable_without_api_key(self):
        backend = OpenAIImageBackend(_FakeSettings(OPENAI_API_KEY=""))
        assert not backend.is_available()
