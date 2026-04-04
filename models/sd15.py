"""SD 1.5 txt2img 로컬 백엔드.

참조 이미지가 없을 때 사용하는 순수 텍스트→이미지 생성 백엔드.
diffusers StableDiffusionPipeline + MPS(Apple Silicon) 지원.
"""

import io
import logging
from pathlib import Path

from schemas.image_schema import ImageGenerationRequest, ImageGenerationResponse

logger = logging.getLogger(__name__)


class SD15Backend:
    """SD 1.5 txt2img 로컬 백엔드.

    첫 호출 시 모델을 lazy 로드하고 이후 재사용합니다.
    Apple Silicon(MPS), CUDA, CPU 순으로 디바이스를 자동 선택합니다.
    """

    def __init__(self, settings) -> None:
        self.settings = settings
        self._pipe = None

    def is_available(self) -> bool:
        """diffusers 패키지가 설치되어 있는지 확인."""
        try:
            import diffusers  # noqa: F401
            import torch  # noqa: F401
            return True
        except ImportError:
            return False

    @property
    def pipe(self):
        """StableDiffusionPipeline lazy 초기화."""
        if self._pipe is not None:
            return self._pipe

        import torch
        from diffusers import StableDiffusionPipeline

        cache_dir = Path(self.settings.LOCAL_MODEL_CACHE_DIR)
        cache_dir.mkdir(parents=True, exist_ok=True)

        if torch.backends.mps.is_available():
            device = "mps"
            dtype = torch.float16
        elif torch.cuda.is_available():
            device = "cuda"
            dtype = torch.float16
        else:
            device = "cpu"
            dtype = torch.float32

        logger.info("SD 1.5 모델 로딩 (device=%s, model=%s)...", device, self.settings.LOCAL_SD15_MODEL_ID)
        pipe = StableDiffusionPipeline.from_pretrained(
            self.settings.LOCAL_SD15_MODEL_ID,
            torch_dtype=dtype,
            cache_dir=str(cache_dir),
        ).to(device)
        logger.info("SD 1.5 모델 로딩 완료")

        self._pipe = pipe
        return self._pipe

    @staticmethod
    def _truncate_prompt(prompt: str, max_tokens: int = 70) -> str:
        """CLIP 최대 토큰(77) 이내로 프롬프트를 단어 단위로 자릅니다."""
        words = prompt.split()
        return " ".join(words[:max_tokens])

    def generate(self, request: ImageGenerationRequest) -> ImageGenerationResponse:
        """텍스트 프롬프트로 이미지 생성."""
        safe_prompt = self._truncate_prompt(request.prompt)
        logger.info("SD 1.5 추론 시작 (steps=%d, prompt=%s...)", self.settings.LOCAL_INFERENCE_STEPS, safe_prompt[:60])

        result = self.pipe(
            prompt=safe_prompt,
            num_inference_steps=self.settings.LOCAL_INFERENCE_STEPS,
            guidance_scale=self.settings.LOCAL_GUIDANCE_SCALE,
        )
        image = result.images[0]

        buf = io.BytesIO()
        image.save(buf, format="PNG")
        logger.info("SD 1.5 추론 완료")

        return ImageGenerationResponse(
            image_data=buf.getvalue(),
            revised_prompt=request.prompt,
        )
