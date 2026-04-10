"""백엔드 레지스트리 — IMAGE_BACKEND_KIND enum 단일 switch (Stage 2).

ImageService / TextService 는 백엔드를 직접 import 하지 않고
이 모듈의 select_image_backend / select_text_backend 만 호출한다.

이미지 백엔드 선택 (settings.IMAGE_BACKEND_KIND):
    MOCK            → MockImageBackend (Pillow 그라데이션, 외부 의존 0)
    HF_LOCAL        → 로컬 diffusers (참조 이미지 + LOCAL_BACKEND 에 따라 분기)
    HF_REMOTE_API   → HFInferenceAPIBackend (Hugging Face Serverless API)
    REMOTE_WORKER   → RemoteWorkerBackend (자체 워커 호출)

텍스트 백엔드 선택:
    무조건 OpenAIGPTBackend (Stage 2 결정 — text 백엔드 분기 폐지).
    Mock 텍스트 백엔드는 여전히 backends/mock_text.py 에 존재하지만 production
    경로에서 선택되지 않는다.
"""

import logging

from backends.image_base import ImageBackend
from backends.text_base import TextBackend
from config.settings import ImageBackendKind

logger = logging.getLogger(__name__)


def select_image_backend(settings, has_reference: bool = False) -> ImageBackend:
    """이미지 생성 백엔드 선택.

    Args:
        settings: 앱 Settings 인스턴스
        has_reference: 요청에 참조 이미지가 포함되어 있는지 여부.
            HF_LOCAL 모드에서 참조 유무에 따라 SD15 vs IP-Adapter/img2img/hybrid 분기.
    """
    kind = settings.IMAGE_BACKEND_KIND

    if kind == ImageBackendKind.MOCK:
        from backends.mock_image import MockImageBackend
        return MockImageBackend(settings)

    if kind == ImageBackendKind.REMOTE_WORKER:
        from backends.remote_worker import RemoteWorkerBackend
        return RemoteWorkerBackend(settings)

    if kind == ImageBackendKind.HF_REMOTE_API:
        from backends.hf_inference_api import HFInferenceAPIBackend
        return HFInferenceAPIBackend(settings)

    if kind == ImageBackendKind.HF_LOCAL:
        return _select_local_image_backend(settings, has_reference)

    # 새 enum 값이 추가되었는데 위에서 처리 안 했을 때만 도달
    raise ValueError(f"알 수 없는 IMAGE_BACKEND_KIND: {kind}")


def _select_local_image_backend(settings, has_reference: bool) -> ImageBackend:
    """로컬 diffusers 백엔드 선택.

    참조 이미지가 없으면 항상 hf_sd15(txt2img).
    있으면 LOCAL_BACKEND 설정에 따라 ip_adapter / img2img / hybrid 중 선택.
    """
    if not has_reference:
        from backends.hf_sd15 import HFSD15Backend
        return HFSD15Backend(settings)

    backend_name = getattr(settings, "LOCAL_BACKEND", "ip_adapter")
    if backend_name == "img2img":
        from backends.hf_img2img import HFImg2ImgBackend
        return HFImg2ImgBackend(settings)
    if backend_name == "hybrid":
        from backends.hf_hybrid import HFHybridBackend
        return HFHybridBackend(settings)

    # 기본값
    from backends.hf_ip_adapter import HFIPAdapterBackend
    return HFIPAdapterBackend(settings)


def select_text_backend(settings) -> TextBackend:
    """텍스트 생성 백엔드 선택 — 무조건 OpenAI (Stage 2 결정)."""
    from backends.openai_gpt import OpenAIGPTBackend
    return OpenAIGPTBackend(settings)
