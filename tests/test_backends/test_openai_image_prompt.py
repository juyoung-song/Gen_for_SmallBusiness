"""backends.openai_image.build_multi_input_prompt 단위 테스트 (Cycle 1 RED→GREEN).

gpt-image-1-mini 의 images.edit 에 [상품 사진, 로고] 두 이미지를 넘길 때,
번역된 영문 프롬프트 앞에 multi-input 안내를 자동으로 덧붙인다.
"""

import pytest

from backends.openai_image import build_multi_input_prompt


class TestCarryTranslatedPrompt:
    def test_english_prompt_is_included(self):
        p = build_multi_input_prompt(
            translated_prompt="commercial bakery photo, natural light"
        )
        assert "commercial bakery photo, natural light" in p

    def test_empty_prompt_raises(self):
        with pytest.raises(ValueError):
            build_multi_input_prompt(translated_prompt="")

    def test_whitespace_only_prompt_raises(self):
        with pytest.raises(ValueError):
            build_multi_input_prompt(translated_prompt="   \n  ")


class TestMultiInputGuidance:
    def test_mentions_first_image_is_product(self):
        p = build_multi_input_prompt(translated_prompt="x").lower()
        assert "first image" in p
        assert "product" in p

    def test_mentions_second_image_is_logo(self):
        p = build_multi_input_prompt(translated_prompt="x").lower()
        assert "second image" in p
        assert "logo" in p or "wordmark" in p

    def test_instructs_logo_engraved_on_props(self):
        p = build_multi_input_prompt(translated_prompt="x").lower()
        # 컵/접시/포장 등 소품에 각인 지시
        hits = sum(
            w in p for w in ["mug", "cup", "plate", "packaging", "napkin"]
        )
        assert hits >= 2

    def test_forbids_distorting_logo(self):
        p = build_multi_input_prompt(translated_prompt="x").lower()
        # 로고 글자 모양 왜곡 금지
        assert "spelling" in p or "exact" in p or "preserve" in p


class TestOutputConstraint:
    def test_output_on_product_photograph_style(self):
        """광고 이미지 컨셉(상품 사진 기반) 이 유지되도록 안내."""
        p = build_multi_input_prompt(translated_prompt="x").lower()
        assert "advertisement" in p or "commercial" in p or "product photography" in p


class TestPositiveBlankDirective:
    """CP16: 부정형 'do not repeat' 대신 긍정형 'leave other props blank'."""

    def test_tail_instructs_other_props_blank(self):
        p = build_multi_input_prompt(translated_prompt="x").lower()
        tail = p.split("x", 1)[1]
        # 나머지 프롭을 명시적으로 비우라는 긍정문
        assert "blank" in tail or "no text" in tail or "no logo" in tail


class TestSandwichReinforcement:
    """CP15-b: 긴 brand_prompt 뒤에 multi-input 지시가 묻히는 문제 완화.

    앞쪽 guidance + 본문 + '뒤에도 한번 더' reminder (샌드위치) 구조.
    """

    def test_wordmark_marked_as_not_a_style_reference(self):
        """SECOND image 가 스타일/팔레트 참조가 아니라는 점을 명시."""
        p = build_multi_input_prompt(translated_prompt="x").lower()
        assert "not a style" in p or "not a color" in p or "not a palette" in p

    def test_has_tail_reminder_after_translated_prompt(self):
        """번역된 본문 뒤에 짧은 재지시(reminder) 가 덧붙는다."""
        body = "UNIQUE_BODY_TOKEN_ZZZ commercial photo"
        p = build_multi_input_prompt(translated_prompt=body)
        idx = p.find(body)
        assert idx != -1
        tail = p[idx + len(body):].lower()
        # 꼬리 부분에도 재지시가 존재해야 함
        assert "reminder" in tail or "mandatory" in tail or "must" in tail

    def test_tail_reminder_mentions_wordmark_on_prop(self):
        """꼬리 재지시가 '워드마크를 소품에 각인/인쇄' 를 명시."""
        body = "UNIQUE_BODY_TOKEN_ZZZ"
        p = build_multi_input_prompt(translated_prompt=body).lower()
        tail = p.split("unique_body_token_zzz", 1)[1]
        assert "wordmark" in tail or "logo" in tail
        hits = sum(w in tail for w in ["mug", "cup", "plate", "packaging", "napkin"])
        assert hits >= 1
