"""Langfuse image generation observation 추적 (hotfix).

backends/openai_image.py 의 _start_image_generation_span 이:
- Langfuse get_client 성공 시 start_as_current_observation(as_type='generation', ...) 을 호출
- Langfuse 비활성/예외 시 nullcontext 로 silent 폴백

실제 OpenAI 호출은 생성하지 않음 (순수 헬퍼 테스트).
"""

from __future__ import annotations

import sys
import types
from contextlib import nullcontext
from unittest.mock import MagicMock

import pytest

from backends.openai_image import _start_image_generation_span


def _install_fake_langfuse(monkeypatch, client):
    """langfuse.get_client 가 주어진 client 를 반환하도록 stub 모듈 주입."""
    fake_mod = types.ModuleType("langfuse")
    fake_mod.get_client = lambda: client
    monkeypatch.setitem(sys.modules, "langfuse", fake_mod)


class TestStartImageGenerationSpan:
    def test_calls_start_as_current_observation_with_generation_type(self, monkeypatch):
        client = MagicMock()
        client.start_as_current_observation.return_value = MagicMock()
        _install_fake_langfuse(monkeypatch, client)

        cm = _start_image_generation_span(
            name="image.edit",
            model="gpt-image-1-mini",
            prompt="commercial bakery photo",
            image_count=3,
            size="1024x1024",
            image_names=["product.png", "logo.png", "ref.png"],
        )

        # 컨텍스트 매니저 리턴 확인
        assert cm is not None
        client.start_as_current_observation.assert_called_once()
        kwargs = client.start_as_current_observation.call_args.kwargs
        assert kwargs["as_type"] == "generation"
        assert kwargs["name"] == "image.edit"
        assert kwargs["model"] == "gpt-image-1-mini"
        assert kwargs["input"]["prompt"] == "commercial bakery photo"
        assert kwargs["input"]["image_count"] == 3
        assert kwargs["input"]["size"] == "1024x1024"
        assert kwargs["input"]["image_names"] == ["product.png", "logo.png", "ref.png"]

    def test_falls_back_to_nullcontext_when_import_fails(self, monkeypatch):
        # langfuse 모듈 import 가 실패하도록 강제
        monkeypatch.setitem(sys.modules, "langfuse", None)

        cm = _start_image_generation_span(
            name="image.edit",
            model="gpt-image-1-mini",
            prompt="x",
            image_count=1,
            size="1024x1024",
            image_names=["a.png"],
        )

        # nullcontext 는 enter/exit 모두 no-op
        assert isinstance(cm, type(nullcontext()))
        with cm as generation:
            assert generation is None

    def test_falls_back_when_get_client_raises(self, monkeypatch):
        def _raising_get_client():
            raise RuntimeError("Langfuse not configured")

        fake_mod = types.ModuleType("langfuse")
        fake_mod.get_client = _raising_get_client
        monkeypatch.setitem(sys.modules, "langfuse", fake_mod)

        cm = _start_image_generation_span(
            name="image.edit",
            model="gpt-image-1-mini",
            prompt="x",
            image_count=1,
            size="1024x1024",
            image_names=["a.png"],
        )

        assert isinstance(cm, type(nullcontext()))
