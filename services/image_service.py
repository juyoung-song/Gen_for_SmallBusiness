"""광고 이미지 생성 서비스.

설계 (compass/context.md, compass/plan.md Step 1.3):
- 백엔드는 backends/ 아래 1파일 1모듈로 분리되어 있다.
- 본 서비스는 백엔드를 직접 import 하지 않고 backends.registry 통해 선택한다.
- 한국어→영문 프롬프트 번역은 본 서비스의 책임이다 (결정 사항: 서비스 책임).
  로컬/HF/원격 워커 모든 백엔드가 영문 프롬프트를 받는다고 가정한다.
- 백엔드는 기술적인 예외(RuntimeError 등)를 발생시키고,
  본 서비스가 ImageServiceError 로 래핑해 UI 에 전달한다.

스토리 이미지 합성(compose_story_image)은 백엔드와 무관한 후처리이므로
계속 본 서비스에 둔다.
"""

import io
import logging

import httpx
from openai import (
    APIConnectionError,
    APITimeoutError,
    AuthenticationError,
    BadRequestError,
    OpenAI,
    RateLimitError,
)
from PIL import Image, ImageDraw

from backends.registry import select_image_backend
from config.settings import Settings
from schemas.image_schema import ImageGenerationRequest, ImageGenerationResponse
from utils.prompt_builder import build_image_prompt

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────
# 커스텀 예외
# ──────────────────────────────────────────────
class ImageServiceError(Exception):
    """이미지 서비스 에러. UI 에 전달할 사용자 친화적 메시지를 담는다."""


class ImageService:
    """광고 이미지 생성 서비스.

    백엔드 선택은 backends.registry.select_image_backend() 가 담당한다.
    본 서비스는 (1) 프롬프트 번역, (2) 백엔드 호출, (3) 예외 래핑만 한다.
    """

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._client: OpenAI | None = None

    @property
    def client(self) -> OpenAI:
        """OpenAI 클라이언트 (lazy 초기화). 프롬프트 번역에만 사용된다."""
        if self._client is None:
            self._client = OpenAI(api_key=self.settings.OPENAI_API_KEY)
        return self._client

    # ──────────────────────────────────────────
    # 메인 진입점
    # ──────────────────────────────────────────
    def generate_ad_image(
        self, request: ImageGenerationRequest
    ) -> ImageGenerationResponse:
        """광고 이미지를 생성하여 반환.

        Mock 모드는 번역을 건너뛰고 백엔드를 바로 호출한다.
        그 외 모드는 한국어 → 영문 번역 후 백엔드에 위임한다.

        Raises:
            ImageServiceError: 백엔드/번역 실패 시 사용자 친화적 메시지
        """
        backend = select_image_backend(
            self.settings,
            has_reference=request.image_data is not None,
        )
        logger.info(
            "이미지 백엔드 선택: %s (has_reference=%s)",
            backend.name,
            request.image_data is not None,
        )

        # Mock 백엔드는 번역 불필요
        if self.settings.USE_MOCK:
            return self._call_backend(backend, request)

        # 그 외 모든 백엔드는 영문 프롬프트 입력 가정 → 번역 수행
        translated_request = self._translate_to_english(request)
        return self._call_backend(backend, translated_request)

    # ──────────────────────────────────────────
    # 프롬프트 한국어 → 영문 번역 (서비스 책임)
    # ──────────────────────────────────────────
    def _translate_to_english(
        self, request: ImageGenerationRequest
    ) -> ImageGenerationRequest:
        """build_image_prompt 결과 한국어 프롬프트를 GPT 로 영문화한 후
        request.prompt 를 갱신한 새 객체를 반환한다."""
        raw_prompt = build_image_prompt(
            product_name=request.product_name,
            description=request.description,
            style=request.style,
            goal=request.goal,
            ad_copy=request.prompt,
            has_reference=(request.image_data is not None),
        )

        try:
            translation = self.client.chat.completions.create(
                model=self.settings.TEXT_MODEL,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "Translate the given Korean description into a concise English prompt "
                            "for Stable Diffusion / FLUX. STRICT LIMIT: under 60 words "
                            "(comma-separated keywords). Output ONLY the English keywords."
                        ),
                    },
                    {"role": "user", "content": raw_prompt},
                ],
                timeout=self.settings.TEXT_TIMEOUT,
            )
        except (
            AuthenticationError,
            RateLimitError,
            APITimeoutError,
            BadRequestError,
            APIConnectionError,
        ) as e:
            logger.error("프롬프트 번역 실패 (OpenAI 에러): %s", e)
            raise ImageServiceError(f"프롬프트 번역 중 오류가 발생했습니다: {e}")
        except Exception as e:
            logger.error("프롬프트 번역 실패 (알 수 없는 오류): %s", e)
            raise ImageServiceError(f"프롬프트 번역 중 오류가 발생했습니다: {e}")

        english_prompt = (translation.choices[0].message.content or "").strip()
        logger.info("영문 프롬프트 번역 완료: %s", english_prompt[:80])

        return request.model_copy(update={"prompt": english_prompt})

    # ──────────────────────────────────────────
    # 백엔드 호출 + 예외 래핑
    # ──────────────────────────────────────────
    def _call_backend(
        self, backend, request: ImageGenerationRequest
    ) -> ImageGenerationResponse:
        if not backend.is_available():
            raise ImageServiceError(
                f"이미지 백엔드({backend.name}) 실행에 필요한 의존성/설정이 부족합니다. "
                f".env 또는 패키지 설치 상태를 확인해주세요."
            )

        try:
            return backend.generate(request)
        except httpx.HTTPStatusError as e:
            raise self._wrap_http_error(e)
        except httpx.TimeoutException:
            logger.error("백엔드(%s) 타임아웃", backend.name)
            raise ImageServiceError(
                f"이미지 생성 시간이 초과되었습니다. 잠시 후 다시 시도해주세요."
            )
        except ImageServiceError:
            raise
        except Exception as e:
            logger.error("백엔드(%s) 호출 오류: %s", backend.name, e)
            raise ImageServiceError(f"이미지 생성 중 예기치 않은 오류가 발생했습니다: {e}")

    @staticmethod
    def _wrap_http_error(e: httpx.HTTPStatusError) -> ImageServiceError:
        status = e.response.status_code
        body = e.response.text
        logger.error("백엔드 HTTP 에러: %s, %s", status, body)
        if status == 401:
            return ImageServiceError("API 키가 유효하지 않습니다.")
        if status == 402:
            return ImageServiceError(
                "AI 생성 무료 사용량이 초과되었습니다. 잠시 후 시도하거나 계정 상태를 확인해주세요."
            )
        if status == 503:
            return ImageServiceError(
                "현재 모델이 초기 로딩(콜드스타트) 중입니다. 약 10~20초 뒤에 다시 시도해주세요!"
            )
        return ImageServiceError(
            f"이미지 생성이 거부되었습니다 (에러 코드: {status})\n상세: {body}"
        )

    # ──────────────────────────────────────────
    # 스토리 이미지 합성 (백엔드 무관 후처리)
    # ──────────────────────────────────────────
    def compose_story_image(self, image_bytes: bytes, text: str) -> bytes:
        """1:1 광고 이미지를 9:16 스토리 포맷으로 합성한다."""
        from PIL import ImageFilter, ImageFont

        img_1x1 = Image.open(io.BytesIO(image_bytes))

        canvas_width, canvas_height = 1080, 1920
        story_canvas = Image.new("RGB", (canvas_width, canvas_height), (255, 255, 255))

        # 배경 — 원본을 꽉 채우고 블러
        bg = img_1x1.copy()
        bg_ratio = canvas_width / canvas_height
        w, h = bg.size
        if w / h > bg_ratio:
            new_w = int(h * bg_ratio)
            left = (w - new_w) // 2
            bg = bg.crop((left, 0, left + new_w, h))
        else:
            new_h = int(w / bg_ratio)
            top = (h - new_h) // 2
            bg = bg.crop((0, top, w, top + new_h))
        bg = bg.resize((canvas_width, canvas_height))
        bg = bg.filter(ImageFilter.GaussianBlur(radius=60))
        story_canvas.paste(bg, (0, 0))

        # 중앙 카드
        img_res = img_1x1.resize((960, 960), Image.Resampling.LANCZOS)
        shadow_margin = 10
        draw = ImageDraw.Draw(story_canvas)
        draw.rectangle(
            [60 - shadow_margin, 480 - shadow_margin, 1020 + shadow_margin, 1440 + shadow_margin],
            fill=(0, 0, 0, 30),
        )
        story_canvas.paste(img_res, (60, 480))

        # 텍스트
        draw = ImageDraw.Draw(story_canvas)
        try:
            font_size = 60
            font = ImageFont.truetype(
                "/System/Library/Fonts/Supplemental/AppleGothic.ttf", font_size
            )
        except Exception:
            font = ImageFont.load_default()

        lines = text.split("\n")
        y_text = 1550
        for line in lines:
            line_w = draw.textlength(line, font=font)
            draw.text(
                ((canvas_width - line_w) / 2, y_text),
                line,
                font=font,
                fill=(255, 255, 255),
            )
            y_text += 80

        buffer = io.BytesIO()
        story_canvas.save(buffer, format="PNG")
        return buffer.getvalue()
