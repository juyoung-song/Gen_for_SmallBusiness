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

    핵심 원칙:
    - **업종은 카페·베이커리·디저트 가게로 고정** (design.md §1.1).
      사용자가 무관한 레퍼런스 URL(예: K-뷰티)을 넣어도 카테고리는 카페/베이커리.
      이런 경우엔 톤·색감·사진 스타일만 추출하고 제품 카테고리는 카페/베이커리로 유지.
    - 이미지가 카페/베이커리/디저트 관련이면 그대로 신뢰.
    - 사용자 자유 텍스트는 보조 단서. 카테고리 충돌 시 사용자 자유 텍스트도 무시 가능.

    LLM 이 이미지를 충실히 관찰하도록 단계적 사고를 강제한다:
    1) 객관적 시각 관찰 — 색감, 사진 스타일, 분위기를 보이는 대로 묘사
    2) 카테고리는 항상 카페/베이커리/디저트 중 하나
    3) 정제된 brand_image 작성
    """
    return (
        "당신은 카페·베이커리·디저트 가게 사장님을 위한 브랜드 아이덴티티\n"
        "컨설턴트입니다. 첨부된 인스타 프로필 캡처 이미지를 기반으로 이 가게의\n"
        "브랜드 정체성을 정제해 주세요.\n"
        "\n"
        "## 업종 고정 (필수)\n"
        "- 본 서비스의 사용자는 **반드시 카페·베이커리·디저트 가게 사장님** 입니다.\n"
        "- 따라서 출력의 '업종/카테고리' 는 항상 카페/베이커리/디저트 중 하나여야 합니다.\n"
        "- 만약 이미지에 다른 업종(예: K-뷰티, 패션, 자동차)의 브랜드가 보이면,\n"
        "  사용자가 단순히 그 브랜드의 톤/감성을 참고하고 싶은 것입니다.\n"
        "  **이 경우 카테고리는 무조건 카페/베이커리/디저트** 로 두고, 이미지에서는\n"
        "  **색감·사진 스타일·분위기·구도** 같은 톤 요소만 참고용으로 추출하세요.\n"
        "  (예: 'Torriden 같은 클린한 민트톤 + 모델 컷의 발랄한 무드를 참고한 베이커리')\n"
        "- 이미지가 카페/베이커리/디저트와 관련된 브랜드라면, 그 브랜드의 시각 정보를\n"
        "  그대로 신뢰하세요.\n"
        "\n"
        "## 사용자가 작성한 자유 텍스트 (보조 단서)\n"
        f'"""\n{user_freetext}\n"""\n'
        "\n"
        "## 작업 단계\n"
        "1) 이미지에서 보이는 객관적 사실을 머릿속으로 정리:\n"
        "   - 주요 색감 (배경/제품/타이포의 컬러 팔레트)\n"
        "   - 사진 스타일 (자연광/스튜디오, 클로즈업/플랫레이/와이드, 소품 사용)\n"
        "   - 분위기 (미니멀/내추럴/모던/빈티지 등)\n"
        "   - 등장하는 인물/오브젝트/그래픽 요소\n"
        "2) 사용자 자유 텍스트에서 카페/베이커리/디저트 운영에 필요한 단서만 추출.\n"
        "   (잘못된 카테고리 단어가 있어도 무시 가능)\n"
        "3) 카테고리는 카페/베이커리/디저트 중 가장 적합한 것을 선택.\n"
        "4) 다음 항목을 포함한 정제된 브랜드 설명을 작성:\n"
        "   - **업종**: 카페 / 베이커리 / 디저트 가게 / 또는 결합형 (예: 베이커리 카페)\n"
        "   - 브랜드 무드와 분위기\n"
        "   - 주요 색감과 톤 (참고 이미지의 색을 본 그대로 — 단, 카페/베이커리에 어울리게 적용)\n"
        "   - 사진 스타일 (자연광/조명/구도/피사체 거리/소품 배치)\n"
        "   - 타깃 고객\n"
        "   - 회피해야 할 요소 (이 브랜드 톤에 어울리지 않는 것)\n"
        "\n"
        "## 출력 형식\n"
        "하나의 자연스러운 한국어 문단 또는 짧은 섹션들. 마크다운 제목/번호 목록은 사용하지\n"
        "마세요. 본문 안에서 '이 브랜드는 ...' 으로 시작하는 자연스러운 서술이면 됩니다.\n"
        "단, 첫 문장에서 반드시 업종(카페/베이커리/디저트)을 명시하세요."
    )


# ──────────────────────────────────────────────
# 도메인 객체
# ──────────────────────────────────────────────
@dataclass(frozen=True)
class BrandImageDraft:
    """GPT Vision 이 생성한 brand_image 초안.

    사용자 검수 화면에서 `with_edited_content()` 로 content 만 수정 가능.
    source_* 는 추적성 보장을 위해 불변.

    Song 이식 필드 (brand_name / brand_color / brand_atmosphere / brand_logo_path):
        온보딩 1단계 입력 섹션에서 수집된 구조화 필드. 모두 선택.
        기존 호출 호환을 위해 기본값 None 또는 빈 문자열.
    """

    content: str
    source_freetext: str
    source_reference_url: str
    source_screenshots: list[str]
    brand_name: str | None = None
    brand_color: str | None = None
    brand_atmosphere: str | None = None
    brand_logo_path: str | None = None

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
        brand_name: str | None = None,
        brand_color: str | None = None,
        brand_atmosphere: str | None = None,
        brand_logo_path: str | None = None,
    ) -> BrandImageDraft:
        """1) 캡처 → 2) Vision 분석 → BrandImageDraft 반환.

        DB 저장은 하지 않는다. 사용자 검수 후 finalize() 를 호출해야 저장됨.

        Song 이식 — 구조화된 브랜드 입력(brand_name/color/atmosphere)은
        GPT Vision 에 더 나은 컨텍스트를 주기 위해 freetext 앞부분에 머지된다.
        brand_logo_path 는 Vision 분석에는 쓰이지 않고 Draft 에 그대로 보존된다.
        """
        logger.info("온보딩 캡처 시작: %s", instagram_url)
        captured = self.capture_backend.capture_profile(
            url=instagram_url,
            out_dir=self.onboarding_dir,
            count=2,
        )
        logger.info("캡처 완료 (%d장). Vision 분석 시작.", len(captured))

        merged_freetext = _merge_structured_inputs_into_freetext(
            freetext=freetext,
            brand_name=brand_name,
            brand_color=brand_color,
            brand_atmosphere=brand_atmosphere,
        )

        content = self.vision_analyzer.analyze(
            freetext=merged_freetext,
            image_paths=captured,
        )
        logger.info("Vision 분석 완료 (%d chars)", len(content))

        return BrandImageDraft(
            content=content,
            source_freetext=freetext,
            source_reference_url=instagram_url,
            source_screenshots=[str(p) for p in captured],
            brand_name=brand_name,
            brand_color=brand_color,
            brand_atmosphere=brand_atmosphere,
            brand_logo_path=brand_logo_path,
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
            brand_name=draft.brand_name,
            brand_color=draft.brand_color,
            brand_atmosphere=draft.brand_atmosphere,
            brand_logo_path=draft.brand_logo_path,
        )


def _merge_structured_inputs_into_freetext(
    *,
    freetext: str,
    brand_name: str | None,
    brand_color: str | None,
    brand_atmosphere: str | None,
) -> str:
    """Vision 분석용 freetext 에 구조화 입력을 앞부분에 프리픽스로 추가.

    테스트 가능한 순수 함수. UI 로 들어온 구조화 필드들을 GPT Vision 프롬프트에
    자연스럽게 녹이기 위한 어댑터.
    """
    prefix_lines: list[str] = []
    if brand_name:
        prefix_lines.append(f"브랜드 이름: {brand_name}")
    if brand_color:
        prefix_lines.append(f"브랜드 대표 색상: {brand_color}")
    if brand_atmosphere:
        prefix_lines.append(f"브랜드 분위기: {brand_atmosphere}")

    if not prefix_lines:
        return freetext

    prefix = "\n".join(prefix_lines)
    return f"{prefix}\n\n{freetext}"
