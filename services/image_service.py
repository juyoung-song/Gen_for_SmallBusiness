"""광고 이미지 생성 서비스.

architecture.md 4.3 기준:
- 광고 이미지 생성 비즈니스 로직
- Mock 모드: Pillow로 스타일별 그라데이션 이미지 생성
- OpenAPI 및 외부 API(Hugging Face) 호출 → 이미지 다운로드

architecture.md 6장 전환 전략:
- USE_MOCK=true → _mock_response() (Pillow 이미지)
- USE_MOCK=false → _api_response() (Hugging Face 호출)
"""

import base64
import io
import logging
import mimetypes
import os

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

from config.settings import Settings
from schemas.image_schema import (
    ImageGenerationRequest,
    ImageGenerationResponse,
    ImageInferenceOptions,
    ReferenceImageContext,
)
from utils.prompt_builder import build_image_prompt

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────
# 커스텀 예외
# ──────────────────────────────────────────────
class ImageServiceError(Exception):
    """이미지 서비스 에러. UI에 전달할 사용자 친화적 메시지를 담는다."""


# ──────────────────────────────────────────────
# 스타일별 그라데이션 색상 (Mock 이미지용)
# ──────────────────────────────────────────────
_STYLE_GRADIENTS: dict[str, tuple[tuple[int, int, int], tuple[int, int, int]]] = {
    "기본": ((41, 128, 185), (52, 152, 219)),
    "감성": ((192, 108, 132), (241, 148, 138)),
    "고급": ((44, 62, 80), (127, 140, 141)),
    "유머": ((243, 156, 18), (247, 220, 111)),
    "심플": ((149, 165, 166), (236, 240, 241)),
}


class ImageService:
    """광고 이미지 생성 서비스.

    settings.USE_MOCK 값에 따라 Mock/API를 자동 전환합니다.
    OpenAI 클라이언트는 API 모드에서 1회만 생성하여 재사용합니다.
    """

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._client: OpenAI | None = None

    @property
    def client(self) -> OpenAI:
        """OpenAI 클라이언트 (lazy 초기화, 재사용)."""
        if self._client is None:
            self._client = OpenAI(api_key=self.settings.OPENAI_API_KEY)
        return self._client

    def _runtime_service(self, request: ImageGenerationRequest) -> "ImageService":
        """요청 단위 추론 옵션이 있으면 해당 설정을 반영한 서비스 인스턴스를 만든다."""
        options = request.inference_options
        if options is None:
            return self

        update_map = {
            "use_local_model": "USE_LOCAL_MODEL",
            "image_model": "IMAGE_MODEL",
            "local_sd15_model_id": "LOCAL_SD15_MODEL_ID",
            "local_backend": "LOCAL_BACKEND",
            "local_inference_steps": "LOCAL_INFERENCE_STEPS",
            "local_guidance_scale": "LOCAL_GUIDANCE_SCALE",
            "local_ip_adapter_scale": "LOCAL_IP_ADAPTER_SCALE",
            "local_img2img_strength": "LOCAL_IMG2IMG_STRENGTH",
            "local_ip_adapter_weight_name": "LOCAL_IP_ADAPTER_WEIGHT_NAME",
        }
        updates = {}
        for option_key, setting_key in update_map.items():
            value = getattr(options, option_key, None)
            if value is not None:
                updates[setting_key] = value

        if not updates:
            return self

        return ImageService(self.settings.model_copy(update=updates))

    @staticmethod
    def _normalize_reference_contexts(
        contexts: list[ReferenceImageContext] | list[dict] | None,
    ) -> list[ReferenceImageContext]:
        """세션/요청에 담긴 참고 이미지 컨텍스트를 모델 리스트로 정규화."""
        if not contexts:
            return []
        normalized: list[ReferenceImageContext] = []
        for context in contexts:
            if isinstance(context, ReferenceImageContext):
                normalized.append(context)
            else:
                normalized.append(ReferenceImageContext.model_validate(context))
        return normalized

    @staticmethod
    def _image_file_to_data_url(image_path: str) -> str:
        """로컬 이미지 파일을 data URL로 변환."""
        mime_type, _ = mimetypes.guess_type(image_path)
        if not mime_type:
            mime_type = "image/png"
        with open(image_path, "rb") as f:
            image_b64 = base64.b64encode(f.read()).decode("utf-8")
        return f"data:{mime_type};base64,{image_b64}"

    @staticmethod
    def _image_bytes_to_data_url(image_bytes: bytes, image_name: str = "") -> str:
        """메모리 상의 이미지 바이트를 data URL로 변환."""
        mime_type, _ = mimetypes.guess_type(image_name)
        if not mime_type:
            mime_type = "image/png"
        image_b64 = base64.b64encode(image_bytes).decode("utf-8")
        return f"data:{mime_type};base64,{image_b64}"

    def _reference_context_to_data_url(self, context: ReferenceImageContext) -> str:
        """참고 이미지 컨텍스트를 data URL로 변환."""
        if context.image_bytes:
            return self._image_bytes_to_data_url(
                context.image_bytes,
                context.image_name or context.label,
            )
        if context.image_path and os.path.exists(context.image_path):
            return self._image_file_to_data_url(context.image_path)
        raise ImageServiceError("참고 이미지 파일을 읽을 수 없습니다.")

    @staticmethod
    def _fallback_reference_analysis(contexts: list[ReferenceImageContext]) -> str:
        """OpenAI 비전 분석 전 간단한 메타데이터 기반 요약."""
        products = ", ".join(
            (
                context.product_name
                or context.label
                or context.image_name
            )
            for context in contexts[:3]
            if context.product_name or context.label or context.image_name
        )
        styles = ", ".join(sorted({context.style for context in contexts if context.style}))
        return (
            f"Reference products: {products}. "
            f"Observed style tags: {styles}. "
            "Synthesize a coherent brand image from the selected references."
        ).strip()

    def _build_reference_analysis(
        self,
        request: ImageGenerationRequest,
    ) -> str:
        """선택한 여러 참고 이미지와 메타데이터를 GPT-5-mini로 분석해 신규 프롬프트용 요약을 만든다."""
        contexts = self._normalize_reference_contexts(request.reference_contexts)
        valid_contexts = [
            context
            for context in contexts
            if (
                context.image_bytes
                or (context.image_path and os.path.exists(context.image_path))
            )
        ]
        if not valid_contexts:
            return ""

        if self.settings.USE_MOCK or not self.settings.is_api_ready:
            return self._fallback_reference_analysis(valid_contexts)

        content: list[dict] = [{
            "type": "input_text",
            "text": (
                "You are analyzing multiple archived marketing images and their metadata to prepare a prompt brief "
                "for generating one new image. Synthesize common visual patterns, not literal copies.\n"
                f"Target product: {request.product_name}\n"
                f"Product description: {request.description}\n"
                f"Brand philosophy: {request.brand_philosophy}\n"
                f"Marketing goal: {request.goal}\n"
                f"Requested style: {request.style}\n"
                "Output ONLY a concise English reference brief with exactly these 6 lines:\n"
                "Mood: ...\n"
                "Composition: ...\n"
                "Product framing: ...\n"
                "Color and lighting: ...\n"
                "Brand cues: ...\n"
                "Avoid: ..."
            ),
        }]

        for idx, context in enumerate(valid_contexts[:6], start=1):
            content.append({
                "type": "input_text",
                "text": (
                    f"[Reference {idx} metadata]\n"
                    f"Source: {context.source}\n"
                    f"Label: {context.label}\n"
                    f"Product: {context.product_name}\n"
                    f"Description: {context.description}\n"
                    f"Style: {context.style}\n"
                    f"Created at: {context.created_at}\n"
                    f"Prompt: {context.revised_prompt}\n"
                    f"Ad copies: {' | '.join(context.ad_copies[:3])}\n"
                    f"Promo sentences: {' | '.join(context.promo_sentences[:2])}"
                ),
            })
            content.append({
                "type": "input_image",
                "image_url": self._reference_context_to_data_url(context),
                "detail": "low",
            })

        try:
            response = self.client.responses.create(
                model="gpt-5-mini",
                input=[{
                    "role": "user",
                    "content": content,
                }],
            )
            analysis = (response.output_text or "").strip()
            if not analysis:
                raise ImageServiceError("참고 이미지 분석 결과가 비어 있습니다.")
            logger.info("참고 이미지 GPT 분석 완료 (references=%d)", len(valid_contexts))
            return analysis
        except Exception as e:
            logger.error("참고 이미지 분석 실패: %s", e)
            raise ImageServiceError(f"참고 이미지 분석 중 오류가 발생했습니다: {e}")

    def _prepare_request_with_reference_analysis(
        self,
        request: ImageGenerationRequest,
    ) -> ImageGenerationRequest:
        """필요 시 참고 이미지 분석 결과를 요청 객체에 주입."""
        normalized_contexts = self._normalize_reference_contexts(request.reference_contexts)
        if not normalized_contexts:
            return request

        analysis = request.reference_analysis.strip() if request.reference_analysis else ""
        if not analysis:
            analysis = self._build_reference_analysis(
                request.model_copy(update={"reference_contexts": normalized_contexts})
            )

        return request.model_copy(
            update={
                "reference_contexts": normalized_contexts,
                "reference_analysis": analysis,
            }
        )

    def generate_ad_image(
        self, request: ImageGenerationRequest
    ) -> ImageGenerationResponse:
        """광고 이미지를 생성하여 반환.

        Args:
            request: 프롬프트와 스타일이 담긴 요청 객체

        Returns:
            이미지 바이너리와 프롬프트가 담긴 응답 객체

        Raises:
            ImageServiceError: 생성 실패 시 사용자 친화적 메시지
        """
        runtime_service = self._runtime_service(request)
        request = runtime_service._prepare_request_with_reference_analysis(request)
        runtime_settings = runtime_service.settings

        if runtime_settings.USE_MOCK:
            logger.info("Mock 모드: Pillow 이미지 생성 (prompt=%s)", request.prompt[:30])
            return runtime_service._mock_response(request)

        if runtime_settings.IMAGE_BACKEND.lower() == "remote":
            logger.info("원격 워커 모드: VM 이미지 워커 호출")
            return runtime_service._remote_response(request)

        if runtime_settings.USE_LOCAL_MODEL:
            logger.info("로컬 모델 모드: diffusers 추론 (has_reference=%s)", request.image_data is not None)
            return runtime_service._local_response(request)

        logger.info("API 모드: Hugging Face 추론 호출 (prompt=%s, model=%s)",
                     request.prompt[:30], runtime_settings.IMAGE_MODEL)
        return runtime_service._api_response(request)

    # ──────────────────────────────────────────
    # Mock 응답 — Pillow 이미지 생성
    # ──────────────────────────────────────────
    def _mock_response(
        self, request: ImageGenerationRequest
    ) -> ImageGenerationResponse:
        """스타일별 그라데이션 Mock 이미지를 Pillow로 생성."""
        img = self._create_gradient_image(request.style)

        buffer = io.BytesIO()
        img.save(buffer, format="PNG")
        image_bytes = buffer.getvalue()

        return ImageGenerationResponse(
            image_data=image_bytes,
            revised_prompt=(
                f"[Mock 이미지] {request.style} 스타일 · "
                f"프롬프트: {request.prompt}"
            ),
        )

    # ──────────────────────────────────────────
    # Hugging Face Inference API 호출
    # ──────────────────────────────────────────
    def _api_response(
        self, request: ImageGenerationRequest
    ) -> ImageGenerationResponse:
        """Hugging Face API를 호출하여 광고 이미지를 생성.

        Raises:
            ImageServiceError: API 호출 실패 시
        """
        if not self.settings.is_huggingface_ready:
            raise ImageServiceError(
                "Hugging Face API 키가 설정되지 않았습니다. "
                ".env 파일에서 HUGGINGFACE_API_KEY를 발급받아 설정해주세요."
            )

        raw_image_prompt = build_image_prompt(
            product_name=request.product_name,
            description=request.description,
            brand_philosophy=request.brand_philosophy,
            reference_analysis=request.reference_analysis,
            style=request.style,
            goal=request.goal,
            ad_copy=request.prompt,
            has_reference=(request.image_data is not None),
            is_new_product=request.is_new_product,
            is_renewal_product=request.is_renewal_product,
            attachment_count=request.attachment_count,
        )

        try:
            # 1. GPT(TEXT_MODEL)를 이용해 한국어 입력을 고품질 영어 프롬프트로 번역 (HF 최적화)
            logger.info("GPT를 이용한 영어 이미지 프롬프트 번역(최적화) 진행 중...")
            translation_response = self.client.chat.completions.create(
                model=self.settings.TEXT_MODEL,
                messages=[
                    {
                        "role": "system", 
                        "content": "You are an expert prompt engineer for Stable Diffusion and FLUX models. Translate and enhance the given Korean description into a highly detailed, comma-separated English prompt suitable for high-quality image generation. Output ONLY the English keywords, with no conversational text."
                    },
                    {"role": "user", "content": raw_image_prompt}
                ],
                timeout=self.settings.TEXT_TIMEOUT,
            )
            
            english_image_prompt = translation_response.choices[0].message.content.strip()
            logger.info("번역 완료된 최종 영문 프롬프트: %s", english_image_prompt)

            # 2. Hugging Face의 신규 Serverless Inference 라우터 호출
            # Hugging Face의 권장 최신 Serverless Inference 라우터 호출
            api_url = f"https://router.huggingface.co/hf-inference/models/{self.settings.IMAGE_MODEL}"
            headers = {"Authorization": f"Bearer {self.settings.HUGGINGFACE_API_KEY}"}
            payload = {"inputs": english_image_prompt}
            
            logger.info("HF 추론 API 호출 (url=%s)", api_url)
            response = httpx.post(
                api_url, 
                headers=headers, 
                json=payload, 
                timeout=self.settings.IMAGE_TIMEOUT
            )
            response.raise_for_status()

            image_bytes = response.content
            if not image_bytes:
                raise ImageServiceError("Hugging Face API가 응답으로 비어있는 이미지를 반환했습니다.")

            logger.info("HF 이미지 생성 완료 (size=%d bytes)", len(image_bytes))

            return ImageGenerationResponse(
                image_data=image_bytes,
                revised_prompt=english_image_prompt,
            )

        except ImageServiceError:
            raise
        except httpx.HTTPStatusError as e:
            logger.error("HF 다운로드 HTTP 에러: %s, %s", e.response.status_code, e.response.text)
            if e.response.status_code == 401:
                raise ImageServiceError("Hugging Face API 키가 유효하지 않습니다.")
            elif e.response.status_code == 503:
                # HF 추론 엔진 특유의 초기화 딜레이 처리
                raise ImageServiceError("현재 Hugging Face 모델이 초기 로딩(콜드스타트) 중입니다. 약 10~20초 뒤에 다시 시도해주세요!")
            if e.response.status_code == 402:
                raise ImageServiceError("AI 생성 무료 사용량이 초과되었습니다. 잠시 후 시도하거나 유료 계정을 확인해주세요.")
            if e.response.status_code != 200:
                raise ImageServiceError(f"이미지 생성이 거부되었습니다 (에러 코드: {e.response.status_code})\n상세: {e.response.text}")
            raise ImageServiceError(f"이미지 생성이 거부되었습니다 (에러 코드: {e.response.status_code})")
        except httpx.TimeoutException:
            logger.error("Hugging Face API 타임아웃")
            raise ImageServiceError(f"이미지 생성 시간이 초과되었습니다 ({self.settings.IMAGE_TIMEOUT}초). 서버가 바쁠 수 있으니 재시도해주세요.")
        except Exception as e:
            logger.error("이미지 생성 예외: %s", e)
            raise ImageServiceError(f"이미지 생성 중 예기치 않은 오류가 발생했습니다: {e}")

    # ──────────────────────────────────────────
    # 원격 이미지 워커 호출
    # ──────────────────────────────────────────
    def _remote_response(
        self, request: ImageGenerationRequest
    ) -> ImageGenerationResponse:
        """원격 VM 이미지 워커를 호출하여 이미지를 생성."""
        if not self.settings.is_image_worker_ready:
            raise ImageServiceError(
                "원격 이미지 워커 설정이 비어 있습니다. "
                ".env 파일의 IMAGE_WORKER_URL, IMAGE_WORKER_TOKEN을 확인해주세요."
            )

        api_url = f"{self.settings.IMAGE_WORKER_URL.rstrip('/')}/generate-image"
        headers = {
            "Authorization": f"Bearer {self.settings.IMAGE_WORKER_TOKEN}",
        }
        payload = {
            "prompt": request.prompt,
            "product_name": request.product_name,
            "description": request.description,
            "brand_philosophy": request.brand_philosophy,
            "goal": request.goal,
            "style": request.style,
            "is_new_product": request.is_new_product,
            "is_renewal_product": request.is_renewal_product,
            "attachment_count": request.attachment_count,
            "reference_analysis": request.reference_analysis,
            "image_data_b64": (
                base64.b64encode(request.image_data).decode("utf-8")
                if request.image_data
                else None
            ),
            "inference_options": (
                request.inference_options.model_dump(exclude_none=True)
                if request.inference_options
                else None
            ),
        }

        try:
            response = httpx.post(
                api_url,
                headers=headers,
                json=payload,
                timeout=self.settings.IMAGE_WORKER_TIMEOUT,
            )
            response.raise_for_status()
            data = response.json()
            image_data_b64 = data.get("image_data_b64", "")
            if not image_data_b64:
                raise ImageServiceError("원격 이미지 워커가 이미지를 반환하지 않았습니다.")

            return ImageGenerationResponse(
                image_data=base64.b64decode(image_data_b64),
                revised_prompt=data.get("revised_prompt", ""),
            )
        except ImageServiceError:
            raise
        except httpx.HTTPStatusError as e:
            detail = e.response.text
            if e.response.status_code == 401:
                raise ImageServiceError("원격 이미지 워커 토큰이 유효하지 않습니다.")
            raise ImageServiceError(
                f"원격 이미지 워커 호출이 실패했습니다 (에러 코드: {e.response.status_code})\n상세: {detail}"
            )
        except httpx.TimeoutException:
            raise ImageServiceError(
                f"원격 이미지 워커 응답 시간이 초과되었습니다 ({self.settings.IMAGE_WORKER_TIMEOUT:.0f}초)."
            )
        except Exception as e:
            raise ImageServiceError(f"원격 이미지 워커 호출 중 오류가 발생했습니다: {e}")

    # ──────────────────────────────────────────
    # 로컬 diffusers 추론 (SD 1.5 / IP-Adapter)
    # ──────────────────────────────────────────
    def _local_response(
        self, request: ImageGenerationRequest
    ) -> ImageGenerationResponse:
        """로컬 diffusers 모델로 이미지 생성.

        참조 이미지 유무에 따라 백엔드를 자동 선택합니다.
        - image_data 있음 → IPAdapterBackend (참조 이미지 스타일 반영)
        - image_data 없음 → SD15Backend (순수 txt2img)

        Raises:
            ImageServiceError: diffusers 미설치 또는 추론 실패 시
        """
        from models.ip_adapter import IPAdapterBackend
        from models.sd15 import SD15Backend

        # GPT로 한글 프롬프트 → 영어 번역
        raw_prompt = build_image_prompt(
            product_name=request.product_name,
            description=request.description,
            brand_philosophy=request.brand_philosophy,
            reference_analysis=request.reference_analysis,
            style=request.style,
            goal=request.goal,
            ad_copy=request.prompt,
            has_reference=(request.image_data is not None),
            is_new_product=request.is_new_product,
            is_renewal_product=request.is_renewal_product,
            attachment_count=request.attachment_count,
        )
        try:
            translation = self.client.chat.completions.create(
                model=self.settings.TEXT_MODEL,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "Translate the given Korean description into a concise English prompt "
                            "for Stable Diffusion. "
                            "STRICT LIMIT: output must be under 60 words (comma-separated keywords). "
                            "Output ONLY the English keywords, no sentences, no extra text."
                        ),
                    },
                    {"role": "user", "content": raw_prompt},
                ],
                timeout=self.settings.TEXT_TIMEOUT,
            )
            english_prompt = translation.choices[0].message.content.strip()
            logger.info("영문 프롬프트 번역 완료: %s", english_prompt[:80])
        except Exception as e:
            raise ImageServiceError(f"프롬프트 번역 중 오류가 발생했습니다: {e}")

        # 참조 이미지 유무 + LOCAL_BACKEND 설정에 따라 백엔드 선택
        if request.image_data:
            backend_name = getattr(self.settings, "LOCAL_BACKEND", "ip_adapter")
            if backend_name == "img2img":
                from models.img2img import Img2ImgBackend
                backend = Img2ImgBackend(self.settings)
            elif backend_name == "hybrid":
                from models.hybrid import HybridBackend
                backend = HybridBackend(self.settings)
            else:  # "ip_adapter" (기본값)
                backend = IPAdapterBackend(self.settings)
        else:
            backend = SD15Backend(self.settings)

        if not backend.is_available():
            raise ImageServiceError(
                "로컬 모델 실행에 필요한 패키지가 설치되지 않았습니다. "
                "다음 명령어로 설치해주세요:\n"
                "pip install diffusers>=0.24.0 transformers>=4.35.0 accelerate>=0.24.0 torch>=2.1.0"
            )

        translated_request = request.model_copy(update={"prompt": english_prompt})
        try:
            return backend.generate(translated_request)
        except Exception as e:
            logger.error("로컬 추론 오류: %s", e)
            raise ImageServiceError(f"로컬 이미지 생성 중 오류가 발생했습니다: {e}")

    def compose_story_image(self, image_bytes: bytes, text: str) -> bytes:
        """Pillow를 사용하여 1:1 광고 이미지를 9:16 스토리 포맷으로 인스타그램 레퍼런스 스타일로 합성합니다."""
        from PIL import ImageFilter, ImageFont
        
        # 1. 1:1 원본 이미지 로드
        img_1x1 = Image.open(io.BytesIO(image_bytes))
        
        # 2. 9:16 캔버스 생성 (표준 1080x1920)
        canvas_width, canvas_height = 1080, 1920
        story_canvas = Image.new("RGB", (canvas_width, canvas_height), (255, 255, 255))
        
        # 3. 배경 레이어: 원본을 꽉 채우고 블러 처리 (Reference 스타일)
        # 비율 유지를 위해 crop 후 resize
        bg = img_1x1.copy()
        bg_ratio = canvas_width / canvas_height
        w, h = bg.size
        if w/h > bg_ratio:
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
        
        # 4. 중앙에 원본 1:1 이미지 배치 (고급스러운 카드 느낌을 위해 약간의 그림자/여백)
        img_res = img_1x1.resize((960, 960), Image.Resampling.LANCZOS)
        # 그림자 효과 (테두리 대체)
        shadow_margin = 10
        draw = ImageDraw.Draw(story_canvas)
        draw.rectangle(
            [60-shadow_margin, 480-shadow_margin, 1020+shadow_margin, 1440+shadow_margin],
            fill=(0, 0, 0, 30)
        )
        story_canvas.paste(img_res, (60, 480)) # 가로 여백 60씩, 중앙 배치
        
        # 5. 텍스트 오버레이 (상단 또는 하단 여백 활용)
        draw = ImageDraw.Draw(story_canvas)
        
        # 폰트 로드 시도 (실제 환경에 따라 경로 조정 필요, 없으면 디폴트)
        try:
            # macOS NanumGothic 또는 기본 폰트 경로
            font_size = 60
            font = ImageFont.truetype("/System/Library/Fonts/Supplemental/AppleGothic.ttf", font_size)
        except:
            font = ImageFont.load_default()
            
        # 텍스트 줄바꿈 및 중앙 정렬 (매우 짧은 카피이므로 1~2줄 가정)
        lines = text.split('\n')
        y_text = 1550 # 하단 영역
        for line in lines:
            # draw.textbbox 등으로 중앙 정렬 계산 (ImageDraw v9.2+)
            w = draw.textlength(line, font=font)
            draw.text(((canvas_width - w) / 2, y_text), line, font=font, fill=(255, 255, 255))
            y_text += 80

        buffer = io.BytesIO()
        story_canvas.save(buffer, format="PNG")
        return buffer.getvalue()


    # ──────────────────────────────────────────
    # Mock 이미지 생성 헬퍼
    # ──────────────────────────────────────────
    @staticmethod
    def _create_gradient_image(style: str) -> Image.Image:
        """스타일에 맞는 그라데이션 이미지를 생성 (512x512)."""
        width, height = 512, 512
        color_top, color_bottom = _STYLE_GRADIENTS.get(
            style, _STYLE_GRADIENTS["기본"]
        )

        img = Image.new("RGB", (width, height))
        draw = ImageDraw.Draw(img)

        for y in range(height):
            ratio = y / height
            r = int(color_top[0] + (color_bottom[0] - color_top[0]) * ratio)
            g = int(color_top[1] + (color_bottom[1] - color_top[1]) * ratio)
            b = int(color_top[2] + (color_bottom[2] - color_top[2]) * ratio)
            draw.line([(0, y), (width, y)], fill=(r, g, b))

        # 장식 — 반투명 원형 포인트들
        overlay = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        overlay_draw = ImageDraw.Draw(overlay)

        circles = [
            (100, 120, 80, 30),
            (350, 200, 60, 20),
            (200, 380, 100, 15),
            (420, 420, 50, 25),
            (80, 350, 40, 20),
        ]
        for cx, cy, radius, alpha in circles:
            overlay_draw.ellipse(
                [cx - radius, cy - radius, cx + radius, cy + radius],
                fill=(255, 255, 255, alpha),
            )

        img = img.convert("RGBA")
        img = Image.alpha_composite(img, overlay)
        img = img.convert("RGB")

        draw = ImageDraw.Draw(img)
        draw.rectangle(
            [width // 4, height // 2 - 1, 3 * width // 4, height // 2 + 1],
            fill=(255, 255, 255),
        )

        return img
