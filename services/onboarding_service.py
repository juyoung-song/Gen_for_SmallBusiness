"""온보딩 서비스 — brand_image 자동 생성 파이프라인.

design.md §3 흐름:
  1. 사용자 자유 텍스트 + 인스타 프로필 URL 입력
  2. 인스타 캡처 (InstaCaptureBackend)
  3. GPT Vision 분석 → brand_image 초안 생성 (BrandImageDraft)
  4. 사용자 검수 화면에서 초안 수정 가능
  5. 확정 → BrandImageService 를 통해 DB 저장

본 서비스는 (2)~(3), (5) 를 담당한다. UI 라우팅과 (4) 검수 화면은 ui/onboarding.py.

외부 의존성(InstaCaptureBackend, GPT Vision)은 생성자로 주입받아 테스트 가능하게 한다.
"""

from __future__ import annotations

import base64
import logging
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Protocol

from openai import OpenAI

from config.settings import Settings
from models.brand_image import BrandImage
from services.brand_image_service import BrandImageService

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────
# Vision 분석 프롬프트 빌더 (단위 테스트 대상)
# ──────────────────────────────────────────────
def build_vision_analysis_prompt(user_freetext: str) -> str:
    """GPT Vision 호출의 system prompt.

    핵심 원칙 (이미지 우선):
    - 첨부된 인스타 프로필 캡처 이미지가 **사실의 출처(source of truth)**.
    - 사용자 자유 텍스트는 톤/감성에 대한 보조 단서일 뿐, 시각 사실보다 우선하지 않음.
    - 둘이 충돌하면 (예: 자유 텍스트 "베이커리" vs 이미지 "스킨케어 브랜드") **이미지 우선**.

    LLM 이 이미지를 충실히 관찰하도록 단계적 사고를 강제한다:
    1) 객관적 시각 관찰 — 브랜드명, 제품 종류, 색감, 사진 스타일을 실제로 보이는 대로 묘사
    2) 자유 텍스트는 보조 정보로 참고
    3) 정제된 brand_image 작성
    """
    return (
        "당신은 브랜드 아이덴티티 컨설턴트입니다. 첨부된 인스타 프로필 캡처 이미지를\n"
        "기반으로 이 브랜드의 정체성을 정제해 주세요.\n"
        "\n"
        "## 입력 신뢰도\n"
        "- **이미지가 사실의 출처입니다.** 첨부된 캡처에 보이는 브랜드명, 제품, 색감,\n"
        "  사진 스타일이 모든 판단의 근거입니다.\n"
        "- 사용자 자유 텍스트는 보조 단서일 뿐입니다. 이미지에서 관찰한 내용과 충돌하면\n"
        "  **반드시 이미지를 우선**하세요. 사용자가 잘못된 카테고리(예: '베이커리')를 적었어도\n"
        "  이미지에 스킨케어 제품이 보이면 스킨케어 브랜드로 판단해야 합니다.\n"
        "\n"
        "## 사용자가 작성한 자유 텍스트 (보조 단서)\n"
        f'"""\n{user_freetext}\n"""\n'
        "\n"
        "## 작업 단계\n"
        "1) 먼저 이미지에서 보이는 객관적 사실을 머릿속으로 정리하세요:\n"
        "   - 브랜드명/로고 (캡처에서 읽을 수 있는 텍스트)\n"
        "   - 제품 종류와 카테고리 (실제로 무엇을 파는 브랜드인가)\n"
        "   - 주요 색감과 사진 스타일 (배경, 조명, 구도, 소품)\n"
        "   - 등장하는 인물/오브젝트/장면\n"
        "2) 위 관찰을 바탕으로 자유 텍스트가 부합하는 부분만 선택적으로 활용하세요.\n"
        "3) 다음 항목을 포함한 정제된 브랜드 설명을 작성하세요:\n"
        "   - 브랜드 카테고리 (예: 스킨케어, 베이커리, 카페, 패션 등 — 이미지에서 본 그대로)\n"
        "   - 무드와 분위기\n"
        "   - 주요 색감과 톤 (이미지에서 실제로 보이는 색)\n"
        "   - 사진 스타일 (자연광/조명/구도/피사체 거리)\n"
        "   - 타깃 고객\n"
        "   - 회피해야 할 요소 (이 브랜드 톤에 어울리지 않는 것)\n"
        "\n"
        "## 출력 형식\n"
        "하나의 자연스러운 한국어 문단 또는 짧은 섹션들. 마크다운 제목/번호 목록은 사용하지\n"
        "마세요. 본문 안에서 '이 브랜드는 ...' 으로 시작하는 자연스러운 서술이면 됩니다."
    )


# ──────────────────────────────────────────────
# 도메인 객체
# ──────────────────────────────────────────────
@dataclass(frozen=True)
class BrandImageDraft:
    """GPT Vision 이 생성한 brand_image 초안.

    사용자 검수 화면에서 `with_edited_content()` 로 content 만 수정 가능.
    source_* 는 추적성 보장을 위해 불변.
    """

    content: str
    source_freetext: str
    source_reference_url: str
    source_screenshots: list[str]

    def with_edited_content(self, new_content: str) -> "BrandImageDraft":
        return replace(self, content=new_content)


# ──────────────────────────────────────────────
# 주입 가능한 외부 의존성 프로토콜
# ──────────────────────────────────────────────
class _CaptureBackendProto(Protocol):
    def capture_profile(
        self, url: str, out_dir: Path, count: int = 2
    ) -> list[Path]: ...


class _VisionAnalyzerProto(Protocol):
    def analyze(
        self, freetext: str, image_paths: list[Path]
    ) -> str: ...


# ──────────────────────────────────────────────
# OpenAI GPT Vision 분석기 (실제 구현)
# ──────────────────────────────────────────────
class GPTVisionAnalyzer:
    """OpenAI Vision API (gpt-4o-mini) 기반 분석기."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._client: OpenAI | None = None

    @property
    def client(self) -> OpenAI:
        if self._client is None:
            self._client = OpenAI(api_key=self.settings.OPENAI_API_KEY)
        return self._client

    def analyze(self, freetext: str, image_paths: list[Path]) -> str:
        """사용자 자유 텍스트 + 이미지들을 종합한 brand_image 본문을 반환."""
        system_prompt = build_vision_analysis_prompt(freetext)

        content_parts: list[dict] = [
            {"type": "text", "text": system_prompt}
        ]
        for p in image_paths:
            if not p.exists():
                logger.warning("분석 이미지 누락: %s", p)
                continue
            b64 = base64.b64encode(p.read_bytes()).decode("utf-8")
            content_parts.append(
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:image/png;base64,{b64}"
                    },
                }
            )

        response = self.client.chat.completions.create(
            model=self.settings.TEXT_MODEL,
            messages=[{"role": "user", "content": content_parts}],
            timeout=self.settings.TEXT_TIMEOUT,
        )
        return (response.choices[0].message.content or "").strip()


# ──────────────────────────────────────────────
# 온보딩 서비스
# ──────────────────────────────────────────────
class OnboardingService:
    """온보딩 파이프라인 오케스트레이터."""

    def __init__(
        self,
        capture_backend: _CaptureBackendProto,
        vision_analyzer: _VisionAnalyzerProto,
        onboarding_dir: Path,
        brand_image_service: BrandImageService | None = None,
    ) -> None:
        self.capture_backend = capture_backend
        self.vision_analyzer = vision_analyzer
        self.onboarding_dir = Path(onboarding_dir)
        self.brand_image_service = brand_image_service

    async def generate_draft(
        self,
        freetext: str,
        instagram_url: str,
    ) -> BrandImageDraft:
        """1) 캡처 → 2) Vision 분석 → BrandImageDraft 반환.

        DB 저장은 하지 않는다. 사용자 검수 후 finalize() 를 호출해야 저장됨.
        """
        logger.info("온보딩 캡처 시작: %s", instagram_url)
        captured = self.capture_backend.capture_profile(
            url=instagram_url,
            out_dir=self.onboarding_dir,
            count=2,
        )
        logger.info("캡처 완료 (%d장). Vision 분석 시작.", len(captured))

        content = self.vision_analyzer.analyze(
            freetext=freetext,
            image_paths=captured,
        )
        logger.info("Vision 분석 완료 (%d chars)", len(content))

        return BrandImageDraft(
            content=content,
            source_freetext=freetext,
            source_reference_url=instagram_url,
            source_screenshots=[str(p) for p in captured],
        )

    async def finalize(
        self,
        draft: BrandImageDraft,
        user_id: str = "default",
    ) -> BrandImage:
        """검수를 마친 draft 를 BrandImage 로 DB 저장."""
        if self.brand_image_service is None:
            raise RuntimeError(
                "OnboardingService 에 brand_image_service 가 주입되지 않았습니다. "
                "finalize() 호출 전에 설정해주세요."
            )
        return await self.brand_image_service.create(
            user_id=user_id,
            content=draft.content,
            source_freetext=draft.source_freetext,
            source_reference_url=draft.source_reference_url,
            source_screenshots=draft.source_screenshots,
        )
