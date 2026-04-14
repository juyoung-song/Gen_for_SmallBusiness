"""PilPlusAiEditor 단위 테스트 (TDD 사이클 6).

PIL 로 베이스 워드마크를 먼저 렌더한 뒤 OpenAI edit 로 변형하는 파이프라인.
Fake 클라이언트를 주입해 실제 API 호출 없이 로직만 검증한다.
"""

from dataclasses import dataclass, field
from typing import Any

import pytest

from logo_gen_exp.pil_plus_ai import PilPlusAiEditor
from logo_gen_exp.tests.conftest import FONT_PATH_KR_MEDIUM


@dataclass
class FakeEditClient:
    """ImageClientProtocol 중 edit_png 만 테스트 더블."""

    response_bytes: bytes = b"PNG_EDITED"
    edit_calls: list[dict[str, Any]] = field(default_factory=list)

    def generate_png(self, *, prompt: str, size: str) -> bytes:  # pragma: no cover
        raise AssertionError("edit 모드 테스트에서 generate_png 호출되면 안 됨")

    def edit_png(self, *, image: bytes, prompt: str, size: str) -> bytes:
        self.edit_calls.append({"image": image, "prompt": prompt, "size": size})
        return self.response_bytes


class TestPipeline:
    def test_returns_edited_bytes_from_client(self):
        fake = FakeEditClient(response_bytes=b"PNG_X")
        editor = PilPlusAiEditor(client=fake, font_path=FONT_PATH_KR_MEDIUM)
        out = editor.edit(
            name="goorm", color_hex="#5562EA", user_instruction="금박 효과"
        )
        assert out == b"PNG_X"

    def test_sends_base_png_as_image(self):
        """client.edit_png 에 전달된 image 는 PIL 렌더 결과 PNG 바이트여야 함."""
        fake = FakeEditClient()
        editor = PilPlusAiEditor(client=fake, font_path=FONT_PATH_KR_MEDIUM)
        editor.edit(name="goorm", color_hex="#5562EA", user_instruction="x")
        assert len(fake.edit_calls) == 1
        sent_image = fake.edit_calls[0]["image"]
        assert sent_image.startswith(b"\x89PNG")

    def test_prompt_is_wrapped_by_build_edit_prompt(self):
        """사용자 지시가 그대로 전달되지 않고 preservation 가드가 둘러싸여 있어야 함."""
        fake = FakeEditClient()
        editor = PilPlusAiEditor(client=fake, font_path=FONT_PATH_KR_MEDIUM)
        editor.edit(
            name="x", color_hex="#000000", user_instruction="수채화 번짐 효과"
        )
        prompt = fake.edit_calls[0]["prompt"]
        assert "수채화 번짐 효과" in prompt
        assert "preservation" in prompt.lower() or "keep" in prompt.lower()

    def test_default_size_1024_square(self):
        fake = FakeEditClient()
        editor = PilPlusAiEditor(client=fake, font_path=FONT_PATH_KR_MEDIUM)
        editor.edit(name="x", color_hex="#000000", user_instruction="x")
        assert fake.edit_calls[0]["size"] == "1024x1024"

    def test_empty_instruction_rejected(self):
        """build_edit_prompt 의 ValueError 가 전파되어야 함."""
        fake = FakeEditClient()
        editor = PilPlusAiEditor(client=fake, font_path=FONT_PATH_KR_MEDIUM)
        with pytest.raises(ValueError):
            editor.edit(name="x", color_hex="#000000", user_instruction="   ")
