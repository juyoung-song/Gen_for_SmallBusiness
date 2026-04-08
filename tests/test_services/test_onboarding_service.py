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

    def test_prompt_instructs_image_takes_precedence_over_freetext(self):
        """이미지와 자유 텍스트가 충돌할 경우 이미지를 우선해야 함을 명시.

        이전 버그: '베이커리' 라는 자유 텍스트와 K-뷰티 인스타 이미지가 들어왔는데
        GPT 가 자유 텍스트만 따라 베이커리 톤 brand_image 를 작성. 이미지 시각
        정보가 무시됨.
        """
        prompt = build_vision_analysis_prompt("아무 텍스트")
        # "우선" / "충돌" / "이미지가 사실" 같은 명시 단서 중 하나는 있어야 함
        assert (
            "우선" in prompt
            or "충돌" in prompt
            or "이미지가 사실" in prompt
            or "이미지를 사실" in prompt
        )

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
