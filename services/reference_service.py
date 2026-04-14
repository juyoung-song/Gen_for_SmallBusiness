"""ReferenceImage 분석 + CRUD 서비스.

docs/schema.md §3.2 기준:
- 참조 이미지는 구도 전용. 색감·무드·브랜드 톤은 출력에 들어가지 않도록
  system prompt 로 강하게 유도.
- source_output_id (GenerationOutput FK) UNIQUE → 같은 게시물을 여러 번 참조로
  골라도 레코드는 1개. upsert_by_source_output 으로 재사용.
"""

from __future__ import annotations

import base64
import logging
from pathlib import Path
from uuid import UUID

from langfuse.openai import OpenAI  # Langfuse auto-trace wrapper
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from config.settings import Settings
from models.generation_output import GenerationOutput
from models.reference_image import ReferenceImage

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────
# 구도 전용 Vision 분석 프롬프트
# ──────────────────────────────────────────────
def build_composition_analysis_prompt() -> str:
    """구도·앵글·프레이밍·배치만 묘사하도록 강제하는 system prompt.

    브랜드 톤 방어선: 색감/무드/스타일/컬러팔레트 단어가 출력에 들어가지 않게 유도.
    """
    return (
        "You are a **visual composition analyst** for product photography.\n"
        "Your job is to describe ONLY the camera composition of the given image:\n"
        "  - camera angle (eye-level / high-angle / low-angle / overhead / 45°)\n"
        "  - framing (close-up / medium shot / wide / extreme close-up)\n"
        "  - subject placement within frame (center / rule-of-thirds / off-center)\n"
        "  - depth of field hint (shallow / deep focus)\n"
        "  - arrangement of objects / props layout\n"
        "  - orientation (portrait / landscape / square)\n"
        "\n"
        "## STRICT RULES (absolute)\n"
        "- DO NOT describe colors, color palette, mood, atmosphere, lighting style, tone, or brand feel.\n"
        "- DO NOT describe the actual product (e.g. 'croissant', 'latte', 'macaron') — just compositional role (e.g. 'central subject').\n"
        "- DO NOT mention texture, material, finish, or aesthetic adjectives (minimal/rustic/modern).\n"
        "- Output 2-4 short English phrases, comma-separated, under 40 words total.\n"
        "- Example good output: 'overhead flat-lay, central subject, symmetric props around, shallow depth'\n"
        "- Example bad output (DO NOT PRODUCE): 'warm golden hour lighting, minimal beige palette, rustic mood'\n"
    )


class ReferenceAnalyzer:
    """OpenAI Vision 기반 구도 분석기."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._client: OpenAI | None = None

    @property
    def client(self) -> OpenAI:
        if self._client is None:
            self._client = OpenAI(api_key=self.settings.OPENAI_API_KEY)
        return self._client

    def analyze(self, image_path: Path) -> str:
        """주어진 이미지의 구도 프롬프트를 반환."""
        system_prompt = build_composition_analysis_prompt()

        if not image_path.exists():
            raise FileNotFoundError(f"참조 이미지 파일 없음: {image_path}")
        b64 = base64.b64encode(image_path.read_bytes()).decode("utf-8")

        response = self.client.chat.completions.create(
            model=self.settings.TEXT_MODEL,
            messages=[{
                "role": "user",
                "content": [
                    {"type": "text", "text": system_prompt},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/png;base64,{b64}"},
                    },
                ],
            }],
            timeout=self.settings.TEXT_TIMEOUT,
        )
        return (response.choices[0].message.content or "").strip()


# ──────────────────────────────────────────────
# ReferenceImage CRUD
# ──────────────────────────────────────────────
class ReferenceImageService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_source_output(
        self, source_output_id: UUID
    ) -> ReferenceImage | None:
        stmt = (
            select(ReferenceImage)
            .where(ReferenceImage.source_output_id == source_output_id)
            .limit(1)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def upsert_by_source_output(
        self,
        *,
        source_output_id: UUID,
        analyzer: ReferenceAnalyzer,
    ) -> ReferenceImage:
        """source_output_id 에 대응하는 ReferenceImage 를 재사용하거나 새로 만든다.

        - 이미 있으면 그대로 반환 (재분석 없음)
        - 없으면 GenerationOutput 의 content_path 를 읽어 구도 분석 → INSERT
        """
        existing = await self.get_by_source_output(source_output_id)
        if existing is not None:
            return existing

        output = await self.session.get(GenerationOutput, source_output_id)
        if output is None:
            raise ValueError(f"GenerationOutput {source_output_id} 가 존재하지 않음")
        if output.kind != "image" or not output.content_path:
            raise ValueError(
                f"GenerationOutput {source_output_id} 는 참조 가능한 이미지가 아님"
            )

        # brand_id 는 generation_output → generation → brand_id 로 추적
        from models.generation import Generation
        gen = await self.session.get(Generation, output.generation_id)
        if gen is None:
            raise ValueError(
                f"GenerationOutput {source_output_id} 의 Generation 을 찾을 수 없음"
            )

        logger.info("참조 이미지 구도 분석 시작: %s", output.content_path)
        composition_prompt = analyzer.analyze(Path(output.content_path))
        logger.info("구도 분석 완료 (%d chars)", len(composition_prompt))

        ref = ReferenceImage(
            brand_id=gen.brand_id,
            source_output_id=source_output_id,
            path=output.content_path,
            composition_prompt=composition_prompt,
        )
        self.session.add(ref)
        await self.session.commit()
        await self.session.refresh(ref)
        return ref
