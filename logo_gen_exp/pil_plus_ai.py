"""PilPlusAiEditor — PIL 베이스 워드마크 + OpenAI edit 변형 파이프라인.

순서:
  1. render_wordmark(name, color_hex, font_path)        → base PNG (글자 정확)
  2. client.edit_png(image=base, prompt=..., size=...)  → 변형 PNG
  3. 변형 결과 반환

장점:
- 글자 모양·스펠링·색상은 PIL 이 보장 (한글 오탈자 0)
- 장식·배경 변형만 AI 가 담당
- build_edit_prompt 가 "글자 보존" 가드를 자동 삽입 → 모델이 함부로 글자 변경 못 함
"""

from __future__ import annotations

from pathlib import Path

from logo_gen_exp.generator import DEFAULT_SIZE, ImageClientProtocol
from logo_gen_exp.pil_renderer import render_wordmark
from logo_gen_exp.prompts import build_edit_prompt


class PilPlusAiEditor:
    """PIL 베이스 렌더 + AI edit 2단 파이프라인."""

    def __init__(
        self,
        client: ImageClientProtocol,
        font_path: Path,
        *,
        size: str = DEFAULT_SIZE,
    ) -> None:
        self.client = client
        self.font_path = font_path
        self.size = size

    def edit(
        self,
        *,
        name: str,
        color_hex: str,
        user_instruction: str,
    ) -> bytes:
        """PIL 베이스 렌더 후 AI edit 호출, 변형된 PNG bytes 반환."""
        base_png = render_wordmark(
            name=name, color_hex=color_hex, font_path=self.font_path
        )
        prompt = build_edit_prompt(user_instruction=user_instruction)
        return self.client.edit_png(image=base_png, prompt=prompt, size=self.size)
