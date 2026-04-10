"""ImageGenerationRequest 스키마 테스트.

design.md §4.1 의 "참조 이미지 = 옵션, 갤러리 다중 선택, 전체 풀" 을 반영하여
reference_image_paths 필드 추가.
"""

from schemas.image_schema import ImageGenerationRequest


class TestImageGenerationRequestReferencePaths:
    def test_default_reference_image_paths_is_empty_list(self):
        """신규 필드 reference_image_paths 는 기본값이 빈 리스트여야 한다."""
        request = ImageGenerationRequest(product_name="블루베리 치즈케이크")
        assert request.reference_image_paths == []

    def test_can_set_multiple_reference_image_paths(self):
        request = ImageGenerationRequest(
            product_name="마들렌",
            reference_image_paths=[
                "data/uploads/a.png",
                "data/uploads/b.png",
                "data/uploads/c.png",
            ],
        )
        assert len(request.reference_image_paths) == 3
        assert request.reference_image_paths[0] == "data/uploads/a.png"

    def test_reference_paths_independent_of_image_data(self):
        """image_data (raw 이미지) 와 reference_image_paths (참조 풀) 은 별개."""
        request = ImageGenerationRequest(
            product_name="스콘",
            image_data=b"raw jpeg bytes",
            reference_image_paths=["data/uploads/previous.png"],
        )
        assert request.image_data == b"raw jpeg bytes"
        assert request.reference_image_paths == ["data/uploads/previous.png"]

    def test_brand_prompt_defaults_to_empty(self):
        """brand_prompt 필드가 기본값 빈 문자열이어야 함 (Step A)."""
        request = ImageGenerationRequest(product_name="무화과 케이크")
        assert request.brand_prompt == ""

    def test_brand_prompt_can_be_set(self):
        request = ImageGenerationRequest(
            product_name="무화과 케이크",
            brand_prompt="이 브랜드는 동네 베이커리로, 따뜻한 목재 톤...",
        )
        assert "동네 베이커리" in request.brand_prompt
