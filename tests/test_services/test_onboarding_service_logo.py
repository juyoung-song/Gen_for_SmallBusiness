"""OnboardingService.finalize 의 로고 자동 생성 통합 테스트 (CP14-2).

- draft.logo_path 가 None 이면 LogoAutoGenerator 가 호출되고 생성된 경로가 저장됨
- draft.logo_path 가 이미 있으면 LogoAutoGenerator 는 호출되지 않고 그대로 유지
- LogoAutoGenerator 가 주입되지 않았다면 logo_path 가 None 그대로 저장 (하위 호환)

외부 의존성(InstaCapture, GPTVision) 은 Protocol 테스트 더블로 대체.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest

from models.brand import Brand
from services.brand_service import BrandService
from services.onboarding_service import (
    BrandDraft,
    OnboardingService,
)


@dataclass
class _FakeCapture:
    def capture_profile(self, url, out_dir, count=2):
        return []


@dataclass
class _FakeVisionAnalyzer:
    reply: str = "이 브랜드는 베이커리 카페입니다."

    def analyze(self, freetext, image_paths):
        return self.reply


@dataclass
class _FakeLogoGenerator:
    """LogoAutoGenerator 의 generate_and_save 만 흉내."""

    save_dir: Path
    calls: list[dict[str, Any]] = field(default_factory=list)

    def generate_and_save(self, *, name: str, color_hex: str) -> Path:
        self.calls.append({"name": name, "color_hex": color_hex})
        self.save_dir.mkdir(parents=True, exist_ok=True)
        out = self.save_dir / "fake_logo.png"
        out.write_bytes(b"\x89PNG\r\n\x1a\n" + b"FAKE")
        return out


class TestLogoAutoGenOnFinalize:
    async def test_generates_logo_when_draft_has_none(self, db_session, tmp_path):
        fake_logo = _FakeLogoGenerator(save_dir=tmp_path / "brand_assets")
        service = OnboardingService(
            capture_backend=_FakeCapture(),
            vision_analyzer=_FakeVisionAnalyzer(),
            onboarding_dir=tmp_path / "onboarding",
            brand_service=BrandService(db_session),
            logo_generator=fake_logo,
        )
        draft = BrandDraft(
            name="구름",
            color_hex="#5562EA",
            logo_path=None,
            input_instagram_url="https://instagram.com/x",
            input_description="d",
            input_mood="m",
            style_prompt="이 브랜드는 베이커리입니다.",
        )
        brand = await service.finalize(draft)

        # Fake 가 호출됐고 brand 에 반영됐는지
        assert len(fake_logo.calls) == 1
        assert fake_logo.calls[0]["name"] == "구름"
        assert fake_logo.calls[0]["color_hex"] == "#5562EA"
        assert brand.logo_path is not None
        assert Path(brand.logo_path).name == "fake_logo.png"
        assert Path(brand.logo_path).exists()

    async def test_keeps_existing_logo_path(self, db_session, tmp_path):
        existing_logo = tmp_path / "user_uploaded.png"
        existing_logo.write_bytes(b"\x89PNG\r\n\x1a\n" + b"USER")
        fake_logo = _FakeLogoGenerator(save_dir=tmp_path / "brand_assets")

        service = OnboardingService(
            capture_backend=_FakeCapture(),
            vision_analyzer=_FakeVisionAnalyzer(),
            onboarding_dir=tmp_path / "onboarding",
            brand_service=BrandService(db_session),
            logo_generator=fake_logo,
        )
        draft = BrandDraft(
            name="구름",
            color_hex="#5562EA",
            logo_path=str(existing_logo),
            input_instagram_url="https://instagram.com/x",
            input_description="d",
            input_mood="m",
            style_prompt="이 브랜드는 베이커리입니다.",
        )
        brand = await service.finalize(draft)

        # Fake 호출되지 않고, 원본 경로 유지
        assert fake_logo.calls == []
        assert brand.logo_path == str(existing_logo)

    async def test_without_logo_generator_keeps_none(self, db_session, tmp_path):
        """logo_generator 를 주입하지 않은 경우에는 기존 동작 유지 — logo_path None 저장."""
        service = OnboardingService(
            capture_backend=_FakeCapture(),
            vision_analyzer=_FakeVisionAnalyzer(),
            onboarding_dir=tmp_path / "onboarding",
            brand_service=BrandService(db_session),
            # logo_generator 미주입
        )
        draft = BrandDraft(
            name="구름",
            color_hex="#5562EA",
            logo_path=None,
            input_instagram_url="https://instagram.com/x",
            input_description="d",
            input_mood="m",
            style_prompt="이 브랜드는 베이커리입니다.",
        )
        brand = await service.finalize(draft)
        assert brand.logo_path is None


class TestBrandDraftWithLogoPath:
    """BrandDraft 자체에 with_logo_path 메서드 추가 (frozen dataclass replace)."""

    def test_with_logo_path_returns_new_draft_with_path(self):
        d = BrandDraft(
            name="x",
            color_hex="#000000",
            logo_path=None,
            input_instagram_url="u",
            input_description="d",
            input_mood="m",
            style_prompt="sp",
        )
        updated = d.with_logo_path("/tmp/logo.png")
        assert updated.logo_path == "/tmp/logo.png"
        assert d.logo_path is None  # 원본 불변

    def test_with_logo_path_preserves_other_fields(self):
        d = BrandDraft(
            name="x",
            color_hex="#FF0000",
            logo_path=None,
            input_instagram_url="u",
            input_description="d",
            input_mood="m",
            style_prompt="sp",
        )
        updated = d.with_logo_path("/tmp/l.png")
        assert updated.color_hex == "#FF0000"
        assert updated.style_prompt == "sp"
