"""IP-Adapter + SD 1.5 로컬 백엔드.

참조 이미지가 있을 때 사용. 사용자 업로드 사진의 색감·구도·분위기를
IP-Adapter cross-attention을 통해 이미지 생성에 직접 반영합니다.
diffusers 0.24+ load_ip_adapter() 사용.
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


@lru_cache(maxsize=6)
def _load_ip_adapter_pipeline(
    model_id: str,
    adapter_id: str,
    adapter_subfolder: str,
    adapter_weight_name: str,
    cache_dir: str,
    device: str,
    dtype_name: str,
):
    import torch
    from diffusers import StableDiffusionPipeline

    logger.info("IP-Adapter 모델 로딩 (device=%s, model=%s)...", device, model_id)
    pipe = StableDiffusionPipeline.from_pretrained(
        model_id,
        torch_dtype=getattr(torch, dtype_name),
        cache_dir=cache_dir,
    ).to(device)
    pipe.load_ip_adapter(
        adapter_id,
        subfolder=adapter_subfolder,
        weight_name=adapter_weight_name,
        cache_dir=cache_dir,
    )
    logger.info("IP-Adapter 모델 로딩 완료 (weight=%s)", adapter_weight_name)
    return pipe


class IPAdapterBackend:
    """IP-Adapter + SD 1.5 로컬 백엔드.

    참조 이미지(request.image_data)가 있으면 IP-Adapter로 스타일을 반영하고,
    없으면 일반 txt2img로 fallback합니다.
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
        """StableDiffusionPipeline + IP-Adapter lazy 초기화."""
        if self._pipe is not None:
            return self._pipe

        cache_dir = Path(self.settings.LOCAL_MODEL_CACHE_DIR)
        cache_dir.mkdir(parents=True, exist_ok=True)
        device, dtype_name = _resolve_device_and_dtype()
        self._pipe = _load_ip_adapter_pipeline(
            self.settings.LOCAL_SD15_MODEL_ID,
            self.settings.LOCAL_IP_ADAPTER_ID,
            self.settings.LOCAL_IP_ADAPTER_SUBFOLDER,
            self.settings.LOCAL_IP_ADAPTER_WEIGHT_NAME,
            str(cache_dir),
            device,
            dtype_name,
        )
        return self._pipe

    @staticmethod
    def _truncate_prompt(prompt: str, max_tokens: int = 70) -> str:
        """CLIP 최대 토큰(77) 이내로 프롬프트를 단어 단위로 자릅니다."""
        words = prompt.split()
        return " ".join(words[:max_tokens])

    def generate(self, request: ImageGenerationRequest) -> ImageGenerationResponse:
        """참조 이미지 + 텍스트 프롬프트로 이미지 생성."""
        from PIL import Image as PILImage

        ref_image = None
        if request.image_data:
            ref_image = PILImage.open(io.BytesIO(request.image_data)).convert("RGB")
            logger.info("참조 이미지 로드 완료 (size=%s)", ref_image.size)
        else:
            logger.warning("image_data 없음 — IP-Adapter가 참조 이미지 없이 실행됩니다.")

        # CLIP 77토큰 제한 초과 시 tuple 에러 방지
        safe_prompt = self._truncate_prompt(request.prompt)
        self.pipe.set_ip_adapter_scale(self.settings.LOCAL_IP_ADAPTER_SCALE)
        logger.info("IP-Adapter 추론 시작 (steps=%d, prompt=%s...)", self.settings.LOCAL_INFERENCE_STEPS, safe_prompt[:60])

        result = self.pipe(
            prompt=safe_prompt,
            ip_adapter_image=ref_image,
            num_inference_steps=self.settings.LOCAL_INFERENCE_STEPS,
            guidance_scale=self.settings.LOCAL_GUIDANCE_SCALE,
        )
        image = result.images[0]

        buf = io.BytesIO()
        image.save(buf, format="PNG")
        logger.info("IP-Adapter 추론 완료")

        return ImageGenerationResponse(
            image_data=buf.getvalue(),
            revised_prompt=request.prompt,
        )
