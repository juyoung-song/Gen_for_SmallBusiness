"""ImageService 의 참조 이미지 처리 테스트.

design.md §4.1.3 + Step 2.2 설계:
- image_data 가 이미 있으면 (raw 이미지) → 그대로 유지, 참조는 무시
- image_data 없고 reference_image_paths 있으면 → 첫 장을 읽어서 image_data 로 주입
- 둘 다 없으면 → image_data=None 그대로

MVP 에서는 백엔드가 다중 참조를 지원하지 않으므로 첫 1장만 사용.
"""

from pathlib import Path

from schemas.image_schema import ImageGenerationRequest
from services.image_service import ImageService


class _FakeSettings:
    is_mock_image = True
    OPENAI_API_KEY = ""
    TEXT_MODEL = "gpt-5-mini"
    TEXT_TIMEOUT = 30.0


class TestResolveReferenceImageData:
    def test_returns_same_request_when_image_data_already_set(self, tmp_path):
        """raw 이미지가 이미 있으면 참조 이미지는 무시된다."""
        service = ImageService(_FakeSettings())
        raw_bytes = b"raw jpeg data"
        ref_path = tmp_path / "ref.png"
        ref_path.write_bytes(b"should not be used")

        request = ImageGenerationRequest(
            product_name="...",
            image_data=raw_bytes,
            reference_image_paths=[str(ref_path)],
        )

        resolved = service._resolve_reference_image_data(request)
        assert resolved.image_data == raw_bytes  # 그대로

    def test_loads_first_reference_when_no_raw_image(self, tmp_path):
        """raw 없고 참조 있으면 첫 장을 image_data 로 주입."""
        service = ImageService(_FakeSettings())
        ref_path = tmp_path / "ref1.png"
        ref_path.write_bytes(b"reference bytes")

        request = ImageGenerationRequest(
            product_name="...",
            image_data=None,
            reference_image_paths=[str(ref_path), str(tmp_path / "ref2.png")],
        )

        resolved = service._resolve_reference_image_data(request)
        assert resolved.image_data == b"reference bytes"

    def test_returns_same_request_when_both_empty(self):
        """raw 도 참조도 없으면 그대로 None."""
        service = ImageService(_FakeSettings())
        request = ImageGenerationRequest(product_name="...")
        resolved = service._resolve_reference_image_data(request)
        assert resolved.image_data is None

    def test_skips_nonexistent_reference_file_gracefully(self, tmp_path):
        """참조 경로가 존재하지 않으면 조용히 image_data=None 으로 둔다."""
        service = ImageService(_FakeSettings())
        request = ImageGenerationRequest(
            product_name="...",
            reference_image_paths=[str(tmp_path / "missing.png")],
        )
        resolved = service._resolve_reference_image_data(request)
        assert resolved.image_data is None
