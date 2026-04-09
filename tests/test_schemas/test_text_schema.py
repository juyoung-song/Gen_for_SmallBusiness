"""TextGenerationRequest 스키마 테스트 (Step A — brand_prompt 필드).

design.md §2.3 / §4.2 기준: 모든 생성 호출에 brand_image.txt 가 주입되어야 한다.
"""

from schemas.text_schema import TextGenerationRequest


class TestTextGenerationRequestBrandPrompt:
    def test_brand_prompt_defaults_to_empty(self):
        """brand_prompt 필드가 기본값 빈 문자열."""
        request = TextGenerationRequest(product_name="무화과 케이크")
        assert request.brand_prompt == ""

    def test_brand_prompt_can_be_set(self):
        request = TextGenerationRequest(
            product_name="무화과 케이크",
            brand_prompt="이 브랜드는 동네 베이커리로...",
        )
        assert "동네 베이커리" in request.brand_prompt
