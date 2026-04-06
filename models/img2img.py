"""SD 1.5 img2img 로컬 백엔드.

참조 이미지를 직접 노이즈화 후 재생성하는 방식.
IP-Adapter와 달리 구도·색감·구조를 높은 충실도로 보존합니다.

strength (0.0~1.0):
  - 낮을수록 원본 보존 (0.3 → 원본 70% 유지)
  - 높을수록 텍스트 프롬프트 영향 증가 (0.7 → 원본 30% 유지)
"""

import io
import logging
from pathlib import Path

from schemas.image_schema import ImageGenerationRequest, ImageGenerationResponse

logger = logging.getLogger(__name__)


class Img2ImgBackend:
    """SD 1.5 img2img 로컬 백엔드.

    참조 이미지가 있을 때 직접 노이즈화 후 재생성합니다.
    참조 이미지가 없으면 ImageServiceError를 발생시킵니다.
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
        """StableDiffusionImg2ImgPipeline lazy 초기화."""
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

        logger.info("img2img 모델 로딩 (device=%s, model=%s)...", device, self.settings.LOCAL_SD15_MODEL_ID)
        self._pipe = StableDiffusionImg2ImgPipeline.from_pretrained(
            self.settings.LOCAL_SD15_MODEL_ID,
            torch_dtype=dtype,
            cache_dir=str(cache_dir),
        ).to(device)
        logger.info("img2img 모델 로딩 완료")
        return self._pipe

    @staticmethod
    def _truncate_prompt(prompt: str, max_tokens: int = 70) -> str:
        words = prompt.split()
        return " ".join(words[:max_tokens])

    def generate(self, request: ImageGenerationRequest) -> ImageGenerationResponse:
        """참조 이미지를 베이스로 텍스트 프롬프트에 맞게 재생성."""
        from PIL import Image as PILImage

        if not request.image_data:
            raise ValueError("img2img 백엔드는 참조 이미지(image_data)가 필요합니다.")

        ref_image = PILImage.open(io.BytesIO(request.image_data)).convert("RGB")
        ref_image = ref_image.resize((512, 512))
        logger.info("참조 이미지 로드 완료 (size=%s)", ref_image.size)

        safe_prompt = self._truncate_prompt(request.prompt)
        strength = getattr(self.settings, "LOCAL_IMG2IMG_STRENGTH", 0.5)
        logger.info(
            "img2img 추론 시작 (steps=%d, strength=%.2f, prompt=%s...)",
            self.settings.LOCAL_INFERENCE_STEPS, strength, safe_prompt[:60],
        )

        result = self.pipe(
            prompt=safe_prompt,
            image=ref_image,
            strength=strength,
            num_inference_steps=self.settings.LOCAL_INFERENCE_STEPS,
            guidance_scale=self.settings.LOCAL_GUIDANCE_SCALE,
        )
        image = result.images[0]

        buf = io.BytesIO()
        image.save(buf, format="PNG")
        logger.info("img2img 추론 완료")

        return ImageGenerationResponse(
            image_data=buf.getvalue(),
            revised_prompt=request.prompt,
        )
