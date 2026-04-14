"""OpenAI 실제 이미지 클라이언트 어댑터 + Langfuse span 래핑.

generator.LogoGenerator 가 기대하는 `ImageClientProtocol` 구현체.
    generate_png(prompt, size) -> bytes

- 모델: gpt-image-1 (기본) — 타이포 렌더링 우수
- 응답: b64_json 으로 받아 bytes 디코딩
- Langfuse: start_as_current_observation(name='logo.autogenerate', as_type='span')
  으로 감싸 prompt / size / trace_id 를 자동 기록. 키 미설정 시 no-op.
"""

from __future__ import annotations

import base64
import contextlib
import logging
from typing import Any

from openai import OpenAI

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "gpt-image-1-mini"


class OpenAIImageClient:
    """OpenAI `images.generate` 호출 + Langfuse span 래핑."""

    def __init__(
        self,
        *,
        api_key: str,
        model: str = DEFAULT_MODEL,
        timeout: float | None = 120.0,
    ) -> None:
        if not api_key:
            raise ValueError("OPENAI_API_KEY 가 설정되어야 합니다")
        self._client = OpenAI(api_key=api_key, timeout=timeout)
        self.model = model
        self._last_trace_id: str | None = None

    @property
    def last_trace_id(self) -> str | None:
        """가장 최근 generate_png 호출의 Langfuse trace_id (실험 UI 표시용)."""
        return self._last_trace_id

    def generate_png(self, *, prompt: str, size: str) -> bytes:
        """이미지 생성 → PNG bytes 반환.

        Langfuse 가 활성 상태면 `logo.autogenerate` span 안에서 호출되어
        자동으로 trace 에 남는다. 비활성이면 nullcontext 로 폴백.
        """
        span_ctx = self._langfuse_span(prompt=prompt, size=size)
        with span_ctx as span:
            # gpt-image-1 은 response_format 파라미터를 받지 않고 항상 b64_json 반환.
            # 명시하면 BadRequestError: Unknown parameter 'response_format'.
            resp = self._client.images.generate(
                model=self.model,
                prompt=prompt,
                size=size,  # type: ignore[arg-type]
                n=1,
            )
            b64 = resp.data[0].b64_json
            if not b64:
                raise RuntimeError("OpenAI 응답에 b64_json 데이터가 없습니다")
            png_bytes = base64.b64decode(b64)

            # span 에 output 메타 기록 + trace_id 추출
            self._last_trace_id = self._extract_trace_id()
            if span is not None:
                try:
                    span.update(
                        output={
                            "bytes_size": len(png_bytes),
                            "trace_id": self._last_trace_id,
                        },
                        metadata={"model": self.model, "size": size},
                    )
                except Exception:  # noqa: BLE001 — 기록 실패가 생성 실패로 번지면 안 됨
                    logger.warning("Langfuse span.update 실패", exc_info=True)

            return png_bytes

    # ──────────────────────────────────────────
    # Langfuse 연동 (미설정 / 실패 시 안전 폴백)
    # ──────────────────────────────────────────

    def _langfuse_span(self, *, prompt: str, size: str) -> Any:
        try:
            from langfuse import get_client

            client = get_client()
            return client.start_as_current_observation(
                name="logo.autogenerate",
                as_type="span",
                input={"prompt": prompt, "size": size},
                metadata={"model": self.model},
            )
        except Exception:  # noqa: BLE001
            logger.debug("Langfuse span 시작 실패 → 추적 없이 진행", exc_info=True)
            return contextlib.nullcontext()

    @staticmethod
    def _extract_trace_id() -> str | None:
        try:
            from langfuse import get_client

            return get_client().get_current_trace_id()
        except Exception:  # noqa: BLE001
            return None
