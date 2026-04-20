"""광고 문구 생성 서비스.

설계 (compass/context.md, compass/plan.md Step 1.3):
- 백엔드는 backends/ 아래 1파일 1모듈로 분리되어 있다.
- 본 서비스는 백엔드를 직접 import 하지 않고 backends.registry 통해 선택한다.
- 백엔드는 기술적인 예외(RuntimeError 등)를 발생시키고,
  본 서비스가 TextServiceError 로 래핑해 UI 에 전달한다.
"""

import logging

from openai import (
    APIConnectionError,
    APITimeoutError,
    AuthenticationError,
    BadRequestError,
    RateLimitError,
)

from backends.registry import select_text_backend
from config.settings import Settings
from schemas.text_schema import TextGenerationRequest, TextGenerationResponse

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────
# 커스텀 예외
# ──────────────────────────────────────────────
class TextServiceError(Exception):
    """텍스트 서비스 에러. UI 에 전달할 사용자 친화적 메시지를 담는다."""


class TextService:
    """광고 문구 생성 서비스.

    백엔드 선택은 backends.registry.select_text_backend() 가 담당한다.
    본 서비스는 (1) 백엔드 호출, (2) 예외 래핑만 한다.
    """

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def generate_ad_copy(
        self, request: TextGenerationRequest
    ) -> TextGenerationResponse:
        """광고 카피 + 홍보 문장 + 스토리 카피를 생성한다.

        Raises:
            TextServiceError: 백엔드 호출 실패 시 사용자 친화적 메시지
        """
        backend = select_text_backend(self.settings)
        logger.info(
            "텍스트 백엔드 선택: %s (product=%s)",
            backend.name,
            request.product_name,
        )

        if not backend.is_available():
            raise TextServiceError(
                f"텍스트 백엔드({backend.name}) 실행에 필요한 설정이 부족합니다. "
                f".env 의 OPENAI_API_KEY 등을 확인해주세요."
            )

        try:
            return backend.generate(request)
        except AuthenticationError:
            logger.error("OpenAI 인증 실패 — API 키를 확인하세요")
            raise TextServiceError(
                "OpenAI API 키가 유효하지 않습니다. "
                ".env 파일의 OPENAI_API_KEY를 확인해주세요."
            )
        except RateLimitError:
            logger.error("OpenAI API 요청 한도 초과")
            raise TextServiceError(
                "API 요청 한도를 초과했습니다. 잠시 후 다시 시도해주세요. "
                "(과금 한도 또는 분당 요청 수 초과)"
            )
        except APITimeoutError:
            logger.error("OpenAI API 타임아웃 (%.0f초)", self.settings.TEXT_TIMEOUT)
            raise TextServiceError(
                f"API 응답 시간이 초과되었습니다 ({self.settings.TEXT_TIMEOUT:.0f}초). "
                "잠시 후 다시 시도해주세요."
            )
        except BadRequestError as e:
            logger.error("OpenAI 잘못된 요청: %s", e)
            raise TextServiceError(f"요청이 거부되었습니다: {e.message}")
        except APIConnectionError:
            logger.error("OpenAI API 연결 실패")
            raise TextServiceError(
                "OpenAI 서버에 연결할 수 없습니다. 네트워크를 확인해주세요."
            )
        except TextServiceError:
            raise
        except Exception as e:
            logger.error("텍스트 생성 예외: %s", e)
            raise TextServiceError(f"문구 생성 중 오류가 발생했습니다: {e}")
