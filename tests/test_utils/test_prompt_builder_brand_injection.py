"""prompt_builder 가 brand_prompt 를 주입하는지 검증 (Step A).

design.md §2.3 / §4.2 기준:
brand_image.txt 본문이 텍스트/이미지 생성 프롬프트에 반드시 반영되어야 한다.
이전 코드는 하드코딩된 _BRAND_CUES 만 쓰고 있었고, 사용자별 brand_image 는
어디에도 주입되지 않는 설계 결함이 있었음.
"""

from utils.prompt_builder import build_image_prompt, build_text_prompt

_SAMPLE_BRAND = (
    "이 브랜드는 동네 베이커리로, 매일 아침 캄파뉴를 굽는 가게입니다. "
    "베이지/브라운/우드 톤과 자연광 중심의 따뜻한 분위기를 선호하며, "
    "과한 채도나 네온 컬러는 피합니다."
)


class TestBuildTextPromptBrandInjection:
    def test_brand_prompt_appears_in_system_prompt(self):
        """build_text_prompt 가 brand_prompt 를 system prompt 안에 포함."""
        system, user = build_text_prompt(
            product_name="무화과 케이크",
            description="존맛",
            style="기본",
            goal="신메뉴 출시",
            brand_prompt=_SAMPLE_BRAND,
        )
        assert "동네 베이커리" in system
        assert "베이지/브라운/우드" in system

    def test_empty_brand_prompt_falls_back_to_default_cues(self):
        """brand_prompt 가 비어 있으면 기존 _BRAND_CUES 가 폴백."""
        system, _ = build_text_prompt(
            product_name="무화과 케이크",
            description="존맛",
            style="기본",
            brand_prompt="",
        )
        # 기본 cue 의 특징적인 문구가 살아 있어야 함
        assert "브랜드 가이드라인" in system

    def test_brand_prompt_parameter_is_optional(self):
        """brand_prompt 미지정 시에도 (기존 호출 호환) 에러 없이 동작."""
        system, user = build_text_prompt(
            product_name="무화과 케이크",
            description="존맛",
            style="기본",
        )
        assert system  # 비어있지 않음


class TestBuildImagePromptBrandInjection:
    def test_brand_prompt_appears_in_image_prompt(self):
        """build_image_prompt 반환 문자열에 brand_prompt 본문이 포함."""
        prompt = build_image_prompt(
            product_name="무화과 케이크",
            description="존맛",
            style="기본",
            goal="신메뉴 출시",
            brand_prompt=_SAMPLE_BRAND,
        )
        assert "동네 베이커리" in prompt or "캄파뉴" in prompt

    def test_empty_brand_prompt_still_returns_valid_prompt(self):
        """brand_prompt 비어 있어도 기존 템플릿 그대로 작동."""
        prompt = build_image_prompt(
            product_name="무화과 케이크",
            description="존맛",
            style="기본",
            goal="신메뉴 출시",
            brand_prompt="",
        )
        assert "무화과 케이크" in prompt  # 상품명은 여전히 포함

    def test_brand_prompt_parameter_is_optional(self):
        """기존 호출 시그니처 호환."""
        prompt = build_image_prompt(
            product_name="무화과 케이크",
            description="존맛",
            style="기본",
            goal="신메뉴 출시",
        )
        assert prompt
