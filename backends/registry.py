"""백엔드 레지스트리 — 환경 변수 기반 백엔드 선택 팩토리.

ImageService / TextService 는 백엔드를 직접 import 하지 않고
이 모듈의 select_image_backend / select_text_backend 만 호출한다.

선택 우선순위 (이미지):
    1. settings.USE_MOCK = True              → MockImageBackend
    2. settings.IMAGE_BACKEND = "remote"     → RemoteWorkerBackend
    3. settings.USE_LOCAL_MODEL = True       → 로컬 diffusers 백엔드 (참조 이미지 + LOCAL_BACKEND 에 따라 분기)
    4. (그 외)                               → HFInferenceAPIBackend

선택 우선순위 (텍스트):
    1. settings.USE_MOCK = True              → MockTextBackend
    2. (그 외)                               → OpenAIGPTBackend
"""

import logging

from backends.image_base import ImageBackend
from backends.text_base import TextBackend

logger = logging.getLogger(__name__)


def select_image_backend(settings, has_reference: bool = False) -> ImageBackend:
    """이미지 생성 백엔드 선택.

    Args:
        settings: 앱 Settings 인스턴스
        has_reference: 요청에 참조 이미지가 포함되어 있는지 여부.
            로컬 모드에서 참조 유무에 따라 SD15 vs IP-Adapter/img2img/hybrid 분기.
    """
    if settings.USE_MOCK:
        from backends.mock_image import MockImageBackend
        return MockImageBackend(settings)

    if settings.IMAGE_BACKEND.lower() == "remote":
        from backends.remote_worker import RemoteWorkerBackend
        return RemoteWorkerBackend(settings)

    if settings.USE_LOCAL_MODEL:
        return _select_local_image_backend(settings, has_reference)

    from backends.hf_inference_api import HFInferenceAPIBackend
    return HFInferenceAPIBackend(settings)


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
    """텍스트 생성 백엔드 선택."""
    if settings.USE_MOCK:
        from backends.mock_text import MockTextBackend
        return MockTextBackend(settings)

    from backends.openai_gpt import OpenAIGPTBackend
    return OpenAIGPTBackend(settings)
