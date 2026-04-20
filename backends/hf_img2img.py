"""SD 1.5 img2img 로컬 백엔드 (Hugging Face diffusers).

참조 이미지를 직접 노이즈화 후 재생성하는 방식.
IP-Adapter와 달리 구도·색감·구조를 높은 충실도로 보존합니다.

strength (0.0~1.0):
  - 낮을수록 원본 보존 (0.3 → 원본 70% 유지)
  - 높을수록 텍스트 프롬프트 영향 증가 (0.7 → 원본 30% 유지)

backends.image_base.ImageBackend 프로토콜 구현.
"""

import io
import logging
from functools import lru_cache
from pathlib import Path

from schemas.image_schema import ImageGenerationRequest, ImageGenerationResponse

logger = logging.getLogger(__name__)


def _resolve_device_and_dtype():
    import torch

    if torch.backends.mps.is_available():
        return "mps", "float16"
    if torch.cuda.is_available():
        return "cuda", "float16"
    return "cpu", "float32"


@lru_cache(maxsize=4)
def _load_img2img_pipeline(model_id: str, cache_dir: str, device: str, dtype_name: str):
    import torch
    from diffusers import StableDiffusionImg2ImgPipeline

    logger.info("img2img 모델 로딩 (device=%s, model=%s)...", device, model_id)
    pipe = StableDiffusionImg2ImgPipeline.from_pretrained(
        model_id,
        torch_dtype=getattr(torch, dtype_name),
        cache_dir=cache_dir,
    ).to(device)
    logger.info("img2img 모델 로딩 완료")
    return pipe


class HFImg2ImgBackend:
    """SD 1.5 img2img 로컬 백엔드 (Hugging Face diffusers).

    참조 이미지가 있을 때 직접 노이즈화 후 재생성합니다.
    참조 이미지가 없으면 ValueError를 발생시킵니다.
    """

    name = "hf_img2img"

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

        cache_dir = Path(self.settings.LOCAL_MODEL_CACHE_DIR)
        cache_dir.mkdir(parents=True, exist_ok=True)
        device, dtype_name = _resolve_device_and_dtype()
        self._pipe = _load_img2img_pipeline(
            self.settings.LOCAL_SD15_MODEL_ID,
            str(cache_dir),
            device,
            dtype_name,
        )
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
