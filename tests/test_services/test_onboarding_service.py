"""OnboardingService 테스트.

design.md §3 온보딩 플로우:
  1. 사용자 자유 텍스트 + 인스타 프로필 URL 입력
  2. 인스타 캡처 (browser-use)
  3. GPT Vision 분석 → brand_image 초안 생성
  4. 사용자 검수 (타협 모드)
  5. 확정 시 BrandImage 레코드 저장

본 서비스는 2~3번과 5번을 담당한다.

테스트 전략:
- InstaCaptureBackend 와 GPT Vision 호출은 외부 의존성이라 가짜로 주입
- 파이프라인 오케스트레이션과 응답 파싱 로직을 단위 테스트
"""

from pathlib import Path
from uuid import UUID

import pytest

from services.brand_image_service import BrandImageService
from services.onboarding_service import (
    BrandImageDraft,
    OnboardingService,
    build_vision_analysis_prompt,
)


class _FakeCaptureBackend:
    """InstaCaptureBackend 의 가짜 구현."""

    def __init__(self, fake_paths: list[Path]):
        self.fake_paths = fake_paths
        self.captured_urls: list[str] = []

    def capture_profile(
        self, url: str, out_dir: Path, count: int = 2
    ) -> list[Path]:
        self.captured_urls.append(url)
        return self.fake_paths


class _FakeVisionAnalyzer:
    """GPT Vision 호출의 가짜 구현."""

    def __init__(self, fake_response: str):
        self.fake_response = fake_response
        self.calls: list[tuple[str, list[Path]]] = []

    def analyze(self, freetext: str, image_paths: list[Path]) -> str:
        self.calls.append((freetext, image_paths))
        return self.fake_response


class TestBuildVisionAnalysisPrompt:
    """사용자 자유 텍스트 → Vision API system prompt 빌더."""

    def test_prompt_includes_user_freetext(self):
        prompt = build_vision_analysis_prompt("따뜻하고 미니멀한 느낌")
        assert "따뜻하고 미니멀한 느낌" in prompt

    def test_prompt_mentions_system_prompt_output_format(self):
        """출력이 system prompt 형태임을 LLM 이 알아야 한다."""
        prompt = build_vision_analysis_prompt("...")
        # "brand" 또는 "system prompt" 중 하나는 프롬프트 안에 있어야 한다
        assert "브랜드" in prompt or "brand" in prompt.lower()

    def test_prompt_mentions_reference_images(self):
        """이미지와 자유 텍스트를 종합하라는 지시가 있어야 한다."""
        prompt = build_vision_analysis_prompt("...")
        assert "이미지" in prompt or "image" in prompt.lower()

    def test_prompt_handles_off_topic_reference_image(self):
        """이미지가 다른 업종이면 카테고리 무시하고 톤만 참고하라는 지시 포함.

        이전 버그 시퀀스:
        - '베이커리' 자유 텍스트 + K-뷰티(Torriden) 인스타 이미지 → 베이커리 톤 결과
          (자유 텍스트만 따라 지어냄)
        - 그 다음 수정: 이미지 우선 → Torriden 스킨케어 brand_image 로 출력
          (사용자는 베이커리인데 K-뷰티 광고가 나오는 꼴)
        - 최종 정책: 카테고리는 항상 카페/베이커리/디저트로 고정. 무관한 이미지는
          톤/색감/사진 스타일만 추출. (design.md §1.1)

        프롬프트에 이 정책의 핵심 키워드 ("톤만" 또는 "톤 + 추출") 가 포함되어야 함.
        """
        prompt = build_vision_analysis_prompt("아무 텍스트")
        # 정책: 무관 이미지는 톤만 추출
        assert "톤" in prompt
        # 카테고리 고정 정책
        assert "고정" in prompt or "반드시" in prompt

    def test_prompt_requires_objective_visual_description_step(self):
        """LLM 이 이미지에서 본 객관적 사실(브랜드명/제품/색)을 먼저 말하도록 강제."""
        prompt = build_vision_analysis_prompt("...")
        # "객관적" / "관찰" / "보이는" / "묘사" 중 하나는 있어야 함
        assert (
            "객관적" in prompt
            or "관찰" in prompt
            or "보이는" in prompt
            or "묘사" in prompt
        )

    def test_prompt_pins_category_to_cafe_bakery_dessert(self):
        """본 MVP 는 카페·베이커리·디저트 가게로 업종이 고정되어 있음 (design.md §1.1).

        프롬프트는 LLM 에게 이 카테고리를 명시적으로 알려야 한다. 사용자가
        무관한 레퍼런스(예: K-뷰티)를 넣어도 카테고리는 카페/베이커리로 유지.
        """
        prompt = build_vision_analysis_prompt("아무 텍스트")
        assert "카페" in prompt
        assert "베이커리" in prompt
        assert "디저트" in prompt

    def test_prompt_instructs_extract_only_tone_when_image_is_off_topic(self):
        """이미지가 다른 업종(뷰티/패션 등)이면 카테고리는 무시하고 톤만 추출."""
        prompt = build_vision_analysis_prompt("...")
        # "톤만" / "참고" / "추출" 같은 지침 단서
        assert "톤만" in prompt or ("톤" in prompt and ("참고" in prompt or "추출" in prompt))


class TestOnboardingServicePipeline:
    """capture → analyze → BrandImageDraft 생성 파이프라인."""

    async def test_generate_draft_runs_capture_and_analysis_in_order(
        self, tmp_path
    ):
        """파이프라인이 정의된 순서대로 동작하고 결과가 BrandImageDraft 에 들어간다."""
        captured_files = [
            tmp_path / "ref_1.png",
            tmp_path / "ref_2.png",
        ]
        # 파일 존재 흉내
        for p in captured_files:
            p.write_bytes(b"fake png")

        capture = _FakeCaptureBackend(fake_paths=captured_files)
        analyzer = _FakeVisionAnalyzer(
            fake_response="따뜻하고 미니멀한 베이커리. 베이지/브라운 톤, 여백 중시."
        )

        service = OnboardingService(
            capture_backend=capture,
            vision_analyzer=analyzer,
            onboarding_dir=tmp_path,
        )

        draft = await service.generate_draft(
            freetext="따뜻한 느낌",
            instagram_url="https://www.instagram.com/some/",
        )

        # 1. capture 가 호출되었는지
        assert capture.captured_urls == ["https://www.instagram.com/some/"]

        # 2. analyzer 가 freetext + 캡처 경로를 받았는지
        assert len(analyzer.calls) == 1
        freetext_arg, paths_arg = analyzer.calls[0]
        assert freetext_arg == "따뜻한 느낌"
        assert paths_arg == captured_files

        # 3. draft 에 분석 결과와 원본 입력이 모두 담겼는지
        assert isinstance(draft, BrandImageDraft)
        assert draft.content == "따뜻하고 미니멀한 베이커리. 베이지/브라운 톤, 여백 중시."
        assert draft.source_freetext == "따뜻한 느낌"
        assert draft.source_reference_url == "https://www.instagram.com/some/"
        assert draft.source_screenshots == [str(p) for p in captured_files]


class TestOnboardingServiceFinalize:
    """사용자 검수 후 BrandImage DB 저장."""

    async def test_finalize_persists_draft_via_brand_image_service(
        self, db_session, tmp_path
    ):
        """draft 를 받아 BrandImageService 를 통해 DB 에 저장."""
        brand_service = BrandImageService(db_session)
        service = OnboardingService(
            capture_backend=_FakeCaptureBackend(fake_paths=[]),
            vision_analyzer=_FakeVisionAnalyzer(fake_response=""),
            onboarding_dir=tmp_path,
            brand_image_service=brand_service,
        )

        draft = BrandImageDraft(
            content="깔끔한 블랙/화이트 카페 톤",
            source_freetext="심플하게",
            source_reference_url="https://example.com/",
            source_screenshots=["data/onboarding/ref_1.png"],
        )

        saved = await service.finalize(draft, user_id="default")

        assert saved is not None
        assert isinstance(saved.id, UUID)
        assert saved.content == "깔끔한 블랙/화이트 카페 톤"
        assert saved.user_id == "default"

        # 실제로 get 가능한지
        loaded = await brand_service.get_for_user("default")
        assert loaded is not None
        assert loaded.id == saved.id

    async def test_user_can_edit_draft_content_before_finalize(
        self, db_session, tmp_path
    ):
        """검수 단계에서 사용자가 content 를 수정한 후 finalize 해도 반영된다."""
        brand_service = BrandImageService(db_session)
        service = OnboardingService(
            capture_backend=_FakeCaptureBackend(fake_paths=[]),
            vision_analyzer=_FakeVisionAnalyzer(fake_response=""),
            onboarding_dir=tmp_path,
            brand_image_service=brand_service,
        )

        draft = BrandImageDraft(
            content="GPT 가 생성한 초안",
            source_freetext="...",
            source_reference_url="https://example.com/",
            source_screenshots=[],
        )

        # 사용자가 수정
        edited_draft = draft.with_edited_content("사용자가 수정한 최종 버전")

        saved = await service.finalize(edited_draft, user_id="default")

        assert saved.content == "사용자가 수정한 최종 버전"


class TestOnboardingStructuredInputs:
    """Song 이식 — 브랜드 이름/색상/로고 등 구조화 입력 파이프라인."""

    async def test_generate_draft_accepts_brand_name_color_atmosphere(self, tmp_path):
        """generate_draft 가 신규 파라미터를 받고 Draft 에 담는다."""
        capture = _FakeCaptureBackend(fake_paths=[])
        analyzer = _FakeVisionAnalyzer(fake_response="정제된 브랜드 설명")

        service = OnboardingService(
            capture_backend=capture,
            vision_analyzer=analyzer,
            onboarding_dir=tmp_path,
        )

        draft = await service.generate_draft(
            freetext="따뜻한 느낌",
            instagram_url="https://example.com/",
            brand_name="구름 베이커리",
            brand_color="#5562EA",
            brand_atmosphere="따뜻하고 단정한",
            brand_logo_path="data/brand/logo.png",
        )

        assert draft.brand_name == "구름 베이커리"
        assert draft.brand_color == "#5562EA"
        assert draft.brand_atmosphere == "따뜻하고 단정한"
        assert draft.brand_logo_path == "data/brand/logo.png"

    async def test_generate_draft_merges_structured_fields_into_vision_freetext(
        self, tmp_path
    ):
        """generate_draft 가 신규 필드를 freetext 에 합쳐 Vision 호출로 전달."""
        capture = _FakeCaptureBackend(fake_paths=[])
        analyzer = _FakeVisionAnalyzer(fake_response="...")
        service = OnboardingService(
            capture_backend=capture,
            vision_analyzer=analyzer,
            onboarding_dir=tmp_path,
        )

        await service.generate_draft(
            freetext="동네 베이커리예요",
            instagram_url="https://example.com/",
            brand_name="구름 베이커리",
            brand_color="#5562EA",
            brand_atmosphere="따뜻하고 단정한",
        )

        # vision analyzer 가 받은 freetext 에 구조화 필드가 포함되어야 함
        assert len(analyzer.calls) == 1
        merged_freetext, _ = analyzer.calls[0]
        assert "구름 베이커리" in merged_freetext
        assert "#5562EA" in merged_freetext
        assert "따뜻하고 단정한" in merged_freetext
        assert "동네 베이커리예요" in merged_freetext

    async def test_finalize_persists_structured_fields(self, db_session, tmp_path):
        """finalize 가 Draft 의 신규 필드를 BrandImage 에 저장."""
        brand_service = BrandImageService(db_session)
        service = OnboardingService(
            capture_backend=_FakeCaptureBackend(fake_paths=[]),
            vision_analyzer=_FakeVisionAnalyzer(fake_response=""),
            onboarding_dir=tmp_path,
            brand_image_service=brand_service,
        )

        draft = BrandImageDraft(
            content="정제된 설명",
            source_freetext="...",
            source_reference_url="https://example.com/",
            source_screenshots=[],
            brand_name="구름 베이커리",
            brand_color="#5562EA",
            brand_atmosphere="따뜻하고 단정한",
            brand_logo_path="data/brand/logo.png",
        )

        saved = await service.finalize(draft, user_id="default")
        assert saved.brand_name == "구름 베이커리"
        assert saved.brand_color == "#5562EA"
        # M3 fix: atmosphere 도 finalize 경로로 persist 돼야 한다
        assert saved.brand_atmosphere == "따뜻하고 단정한"
        assert saved.brand_logo_path == "data/brand/logo.png"
