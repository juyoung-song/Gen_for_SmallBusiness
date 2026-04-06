"""IP-Adapter + img2img 하이브리드 로컬 백엔드.

두 접근을 결합합니다:
1. IP-Adapter: 참조 이미지의 스타일·색감을 cross-attention으로 주입
2. img2img: 참조 이미지를 직접 노이즈화 후 재생성 (구도·구조 보존)

파이프라인 순서:
  참조 이미지
      ├─ IP-Adapter 임베딩 → cross-attention 주입 (스타일)
      └─ 직접 노이즈화 (strength) → 디노이징 베이스 (구조)
      ↓
  결과 이미지 (구조 + 스타일 동시 반영)

strength (0.0~1.0):
  - 낮을수록 원본 구조 보존
  - 높을수록 텍스트/IP-Adapter 영향 증가
IP-Adapter scale (0.0~1.0):
  - 높을수록 참조 이미지 스타일 강하게 반영
"""

import io
import logging
from pathlib import Path

from schemas.image_schema import ImageGenerationRequest, ImageGenerationResponse

logger = logging.getLogger(__name__)


class HybridBackend:
    """IP-Adapter + img2img 하이브리드 로컬 백엔드.

    StableDiffusionImg2ImgPipeline에 IP-Adapter를 로드하여
    구조 보존(img2img)과 스타일 반영(IP-Adapter)을 동시에 수행합니다.
    """

    def __init__(self, settings) -> None:
        self.settings = settings
        self._pipe = None

    def is_available(self) -> bool:
        try:
            import diffusers  # noqa: F401
            import torch  # noqa: F401
            return True
        except ImportError:
            return False

    @property
    def pipe(self):
        """StableDiffusionImg2ImgPipeline + IP-Adapter lazy 초기화."""
        if self._pipe is not None:
            return self._pipe

        import torch
        from diffusers import StableDiffusionImg2ImgPipeline

        cache_dir = Path(self.settings.LOCAL_MODEL_CACHE_DIR)
        cache_dir.mkdir(parents=True, exist_ok=True)

        if torch.backends.mps.is_available():
            device, dtype = "mps", torch.float16
        elif torch.cuda.is_available():
            device, dtype = "cuda", torch.float16
        else:
            device, dtype = "cpu", torch.float32

        logger.info("Hybrid 모델 로딩 (device=%s, model=%s)...", device, self.settings.LOCAL_SD15_MODEL_ID)
        pipe = StableDiffusionImg2ImgPipeline.from_pretrained(
            self.settings.LOCAL_SD15_MODEL_ID,
            torch_dtype=dtype,
            cache_dir=str(cache_dir),
        ).to(device)

        pipe.load_ip_adapter(
            self.settings.LOCAL_IP_ADAPTER_ID,
            subfolder=self.settings.LOCAL_IP_ADAPTER_SUBFOLDER,
            weight_name=self.settings.LOCAL_IP_ADAPTER_WEIGHT_NAME,
            cache_dir=str(cache_dir),
        )
        pipe.set_ip_adapter_scale(self.settings.LOCAL_IP_ADAPTER_SCALE)
        logger.info(
            "Hybrid 모델 로딩 완료 (ip_adapter_scale=%.2f)",
            self.settings.LOCAL_IP_ADAPTER_SCALE,
        )

        self._pipe = pipe
        return self._pipe

    @staticmethod
    def _truncate_prompt(prompt: str, max_tokens: int = 70) -> str:
        words = prompt.split()
        return " ".join(words[:max_tokens])

    def generate(self, request: ImageGenerationRequest) -> ImageGenerationResponse:
        """참조 이미지 기반으로 IP-Adapter + img2img 동시 적용."""
        from PIL import Image as PILImage

        if not request.image_data:
            raise ValueError("Hybrid 백엔드는 참조 이미지(image_data)가 필요합니다.")

        ref_image = PILImage.open(io.BytesIO(request.image_data)).convert("RGB")
        ref_image = ref_image.resize((512, 512))
        logger.info("참조 이미지 로드 완료 (size=%s)", ref_image.size)

        safe_prompt = self._truncate_prompt(request.prompt)
        strength = getattr(self.settings, "LOCAL_IMG2IMG_STRENGTH", 0.5)
        logger.info(
            "Hybrid 추론 시작 (steps=%d, strength=%.2f, ip_scale=%.2f, prompt=%s...)",
            self.settings.LOCAL_INFERENCE_STEPS,
            strength,
            self.settings.LOCAL_IP_ADAPTER_SCALE,
            safe_prompt[:60],
        )

        result = self.pipe(
            prompt=safe_prompt,
            image=ref_image,
            ip_adapter_image=ref_image,
            strength=strength,
            num_inference_steps=self.settings.LOCAL_INFERENCE_STEPS,
            guidance_scale=self.settings.LOCAL_GUIDANCE_SCALE,
        )
        image = result.images[0]

        buf = io.BytesIO()
        image.save(buf, format="PNG")
        logger.info("Hybrid 추론 완료")

        return ImageGenerationResponse(
            image_data=buf.getvalue(),
            revised_prompt=request.prompt,
        )
