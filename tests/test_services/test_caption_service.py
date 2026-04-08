"""CaptionService 테스트 (Mock 모드 분기 - I-2).

USE_MOCK=True 일 때 OpenAI 클라이언트를 호출하지 않고 하드코딩 응답을 반환해야 한다.
기존엔 Mock 분기가 없어서 인증 오류가 발생하는 문제(I-2)가 있었다.
"""

import pytest

from schemas.instagram_schema import CaptionGenerationRequest
from services.caption_service import CaptionService


class _FakeSettings:
    """최소 Settings 스텁. USE_MOCK / OPENAI_API_KEY / TEXT_MODEL / TEXT_TIMEOUT 만."""

    def __init__(self, use_mock: bool):
        self.USE_MOCK = use_mock
        self.OPENAI_API_KEY = ""
        self.TEXT_MODEL = "gpt-4o-mini"
        self.TEXT_TIMEOUT = 30.0


class TestCaptionServiceMockMode:
    def test_mock_mode_returns_hardcoded_caption_without_calling_openai(self):
        """USE_MOCK=True → OpenAI 호출 없이 즉시 응답."""
        service = CaptionService(_FakeSettings(use_mock=True))
        request = CaptionGenerationRequest(
            product_name="블루베리 치즈케이크",
            ad_copies=["✨ 오늘의 디저트", "🎯 프리미엄 품질"],
            style="감성",
        )

        # Mock 모드에선 client 프로퍼티를 접근조차 하지 않아야 한다
        # (API 키 없어도 동작해야 함)
        response = service.generate_caption(request)

        assert response.caption  # 비어있지 않음
        assert response.hashtags  # 비어있지 않음
        # 상품명이 응답에 반영되면 "사용자에게 의미있는 Mock" 이라는 신호
        assert "블루베리 치즈케이크" in response.caption

    def test_mock_mode_does_not_touch_openai_client(self):
        """client 프로퍼티에 접근해서 OpenAI 인스턴스가 만들어지면 안 된다."""
        service = CaptionService(_FakeSettings(use_mock=True))
        request = CaptionGenerationRequest(
            product_name="마들렌",
            ad_copies=["버터 향 가득"],
            style="기본",
        )
        service.generate_caption(request)
        # Mock 분기를 탔으면 _client 가 None 그대로여야 함
        assert service._client is None
