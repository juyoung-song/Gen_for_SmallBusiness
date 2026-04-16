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
import base64
from pathlib import Path

import httpx
from openai import (
    APIConnectionError,
    APITimeoutError,
    AuthenticationError,
    BadRequestError,
    RateLimitError,
)
from langfuse.openai import OpenAI  # Langfuse auto-trace wrapper
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
        # 참조 이미지 구도 선별 (Vision Analysis)
        request = self._analyze_reference_image(request)

        # 참조 이미지 해석: raw image 가 없으면 reference_image_paths 의 첫 장을 주입
        request = self._resolve_reference_image_data(request)

        backend = select_image_backend(
            self.settings,
            has_reference=request.image_data is not None,
        )
        logger.info(
            "이미지 백엔드 선택: %s (has_reference=%s)",
            backend.name,
            request.image_data is not None,
        )

        # Mock 백엔드는 번역 불필요 (외부 호출 안 하므로)
        if self.settings.is_mock_image:
            return self._call_backend(backend, request)

        # 그 외 모든 백엔드는 최적화 수행
        optimized_request = self._optimize_prompt(request)
        return self._call_backend(backend, optimized_request)

    @staticmethod
    def _resolve_reference_image_data(
        request: ImageGenerationRequest,
    ) -> ImageGenerationRequest:
        """참조 이미지 경로를 읽어 image_data 에 주입.

        우선순위:
        1) 이미 image_data 가 있으면 그대로 유지 (raw 이미지가 최우선)
        2) reference_image_paths 의 첫 장이 존재하면 읽어서 image_data 로 주입
        3) 그 외 → image_data=None 유지

        MVP 에서는 백엔드가 다중 참조를 지원하지 않으므로 첫 1장만 사용.
        """
        from pathlib import Path

        if request.image_data is not None:
            return request
        if not request.reference_image_paths:
            return request

        first = Path(request.reference_image_paths[0])
        if not first.exists():
            logger.warning("참조 이미지 파일 누락: %s", first)
            return request

        logger.info("참조 이미지 %s 를 image_data 로 로드", first)
        return request.model_copy(update={"image_data": first.read_bytes()})

    def _analyze_reference_image(self, request: ImageGenerationRequest) -> ImageGenerationRequest:
        """참조 이미지가 있을 경우, GPT Vision을 이용해 구도를 정밀 분석합니다."""
        if not request.reference_image_paths:
            return request

        first_path = request.reference_image_paths[0]
        try:
            with Path(first_path).open("rb") as f:
                base64_image = base64.b64encode(f.read()).decode("utf-8")

            logger.info("참조 이미지 %s 에 대한 Vision 구도 분석 시작", first_path)
            response = self.client.chat.completions.create(
                model=self.settings.TEXT_MODEL,  # Requires Vision capable model
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": "Analyze the composition of this image. Extract ONLY the camera angle (e.g., top view), lens distance (e.g., macro close-up), and subject placement (e.g., bottom-left rule of thirds). Ignore colors and the actual subject/product entirely. Output a very short phrase in English."},
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/jpeg;base64,{base64_image}"
                                }
                            }
                        ]
                    }
                ],
                max_tokens=60,
                timeout=self.settings.TEXT_TIMEOUT,
            )
            analysis_text = response.choices[0].message.content.strip() if response.choices[0].message.content else ""
            logger.info("참조 이미지 구도 분석 완료: %s", analysis_text)
            return request.model_copy(update={"reference_analysis": analysis_text})
        except Exception as e:
            logger.error("Vision 분석 실패, 구도 분석 건너뜀: %s", e)
            return request

    # ──────────────────────────────────────────
    # 프롬프트 gpt-image-1 맞춤 최적화 (Optimization)
    # ──────────────────────────────────────────
    def _optimize_prompt(
        self, request: ImageGenerationRequest
    ) -> ImageGenerationRequest:
        """build_image_prompt 결과물을 gpt-image-1 전용 자연어 비주얼 지시서로 최적화."""
        raw_prompt = build_image_prompt(
            product_name=request.product_name,
            description=request.description,
            style=request.style,
            goal=request.goal,
            ad_copy=request.prompt,
            has_reference=(request.image_data is not None),
            brand_prompt=request.brand_prompt,
            is_new_product=request.is_new_product,
            reference_analysis=request.reference_analysis,
        )

        try:
            optimization = self.client.chat.completions.create(
                name="image.optimize_prompt",  # Langfuse observation 이름
                model=self.settings.TEXT_MODEL,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You are an expert prompt engineer for gpt-image-1. "
                            "Rewrite the user's input into a 100% natural language English visual directive. "
                            "Explicitly instruct the model to transform the first image's product, "
                            "engrave the second image's logo onto a prop with natural perspective, "
                            "and strictly follow any given composition guidelines."
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
            logger.error("프롬프트 최적화 실패 (OpenAI 에러): %s", e)
            raise ImageServiceError(f"프롬프트 최적화 중 오류가 발생했습니다: {e}")
        except Exception as e:
            logger.error("프롬프트 최적화 실패 (알 수 없는 오류): %s", e)
            raise ImageServiceError(f"프롬프트 최적화 중 오류가 발생했습니다: {e}")

        english_prompt = (optimization.choices[0].message.content or "").strip()
        logger.info("영문 프롬프트 최적화 완료: %s", english_prompt[:80])

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
    def _load_story_font(self):
        """스토리 이미지 텍스트용 폰트 로드 (I-4 — Settings 기반).

        settings.STORY_FONT_PATHS 의 콜론 구분 목록을 왼쪽부터 시도한다.
        모두 실패하면 Pillow 기본 폰트로 폴백.
        """
        from PIL import ImageFont

        font_paths = [
            p.strip()
            for p in self.settings.STORY_FONT_PATHS.split(":")
            if p.strip()
        ]
        for path in font_paths:
            try:
                return ImageFont.truetype(path, self.settings.STORY_FONT_SIZE)
            except (OSError, IOError):
                continue
        logger.warning(
            "사용 가능한 한글 폰트를 찾지 못해 Pillow 기본 폰트로 폴백합니다. "
            "STORY_FONT_PATHS 를 환경에 맞게 설정해주세요."
        )
        return ImageFont.load_default()

    def compose_story_image(self, image_bytes: bytes, text: str) -> bytes:
        """1:1 광고 이미지를 9:16 스토리 포맷으로 합성한다."""
        from PIL import ImageFilter

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
        font = self._load_story_font()

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
