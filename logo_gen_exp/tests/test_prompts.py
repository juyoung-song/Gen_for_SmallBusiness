"""build_logo_generation_prompt 단위 테스트 (TDD 사이클 1 RED → GREEN).

검증 대상: 순수 함수. 외부 의존 없음.
"""

import pytest

from logo_gen_exp.prompts import build_logo_generation_prompt


class TestBrandNameAndColor:
    def test_includes_brand_name_in_quotes(self):
        p = build_logo_generation_prompt(name="goorm", color_hex="#5562EA")
        assert '"goorm"' in p

    def test_includes_color_hex_as_is(self):
        p = build_logo_generation_prompt(name="x", color_hex="#FF00AA")
        assert "#FF00AA" in p

    def test_color_hex_case_preserved(self):
        # 소문자로 준 hex 는 그대로 반영 (모델 해석에 영향 없음)
        p = build_logo_generation_prompt(name="x", color_hex="#ff00aa")
        assert "#ff00aa" in p


class TestLanguageBranching:
    def test_english_name_uses_rounded_sans_serif(self):
        p = build_logo_generation_prompt(name="goorm", color_hex="#000000").lower()
        assert "rounded sans-serif" in p
        # 영문 이름에는 Korean 관련 안내가 붙지 않아야 함
        assert "korean" not in p
        assert "hangul" not in p

    def test_korean_name_flags_hangul(self):
        p = build_logo_generation_prompt(name="구름", color_hex="#000000").lower()
        assert ("korean" in p) or ("hangul" in p)

    def test_mixed_name_detected_as_korean(self):
        # 한글이 하나라도 있으면 한글 분기로 판정
        p = build_logo_generation_prompt(name="GOORM 구름", color_hex="#000000").lower()
        assert ("korean" in p) or ("hangul" in p)

    def test_numeric_mixed_english_still_english(self):
        p = build_logo_generation_prompt(name="cafe 21", color_hex="#000000").lower()
        assert "rounded sans-serif" in p
        assert "korean" not in p


class TestForbiddenElements:
    def test_forbids_illustrations_and_icons(self):
        p = build_logo_generation_prompt(name="x", color_hex="#000").lower()
        assert "no illustrations" in p
        assert "no icons" in p

    def test_forbids_shadows_and_3d(self):
        p = build_logo_generation_prompt(name="x", color_hex="#000").lower()
        assert "no shadows" in p
        assert "no 3d" in p

    def test_forbids_backgrounds(self):
        p = build_logo_generation_prompt(name="x", color_hex="#000").lower()
        assert "no backgrounds" in p or "pure white background" in p


class TestPrintingContext:
    def test_mentions_mug_plate_packaging(self):
        p = build_logo_generation_prompt(name="x", color_hex="#000").lower()
        # 컵/접시/포장 중 최소 둘 이상 언급
        hits = sum(word in p for word in ["mug", "plate", "packaging", "napkin"])
        assert hits >= 2

    def test_flat_vector_style(self):
        p = build_logo_generation_prompt(name="x", color_hex="#000").lower()
        assert "flat" in p and "vector" in p
