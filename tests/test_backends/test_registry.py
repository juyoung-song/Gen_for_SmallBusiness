"""backends.registry — enum 기반 단일 switch 테스트.

Stage 2 — IMAGE_BACKEND_KIND enum 값 4종에 대해 정확히 어떤 백엔드가
선택되는지 검증.
"""

from config.settings import ImageBackendKind, Settings


def _make_settings(kind: ImageBackendKind) -> Settings:
    """테스트용 Settings 인스턴스. .env 무시 + 명시 값만."""
    return Settings(_env_file=None, IMAGE_BACKEND_KIND=kind)  # type: ignore[call-arg]


class TestSelectImageBackend:
    def test_mock_kind_returns_mock_image_backend(self):
        from backends.mock_image import MockImageBackend
        from backends.registry import select_image_backend

        s = _make_settings(ImageBackendKind.MOCK)
        backend = select_image_backend(s, has_reference=False)
        assert isinstance(backend, MockImageBackend)

    def test_hf_remote_api_kind_returns_hf_inference_api_backend(self):
        from backends.hf_inference_api import HFInferenceAPIBackend
        from backends.registry import select_image_backend

        s = _make_settings(ImageBackendKind.HF_REMOTE_API)
        backend = select_image_backend(s, has_reference=False)
        assert isinstance(backend, HFInferenceAPIBackend)

    def test_remote_worker_kind_returns_remote_worker_backend(self):
        from backends.registry import select_image_backend
        from backends.remote_worker import RemoteWorkerBackend

        s = _make_settings(ImageBackendKind.REMOTE_WORKER)
        backend = select_image_backend(s, has_reference=False)
        assert isinstance(backend, RemoteWorkerBackend)

    def test_hf_local_no_reference_returns_sd15(self):
        from backends.hf_sd15 import HFSD15Backend
        from backends.registry import select_image_backend

        s = _make_settings(ImageBackendKind.HF_LOCAL)
        backend = select_image_backend(s, has_reference=False)
        assert isinstance(backend, HFSD15Backend)

    def test_hf_local_with_reference_default_returns_ip_adapter(self):
        from backends.hf_ip_adapter import HFIPAdapterBackend
        from backends.registry import select_image_backend

        s = _make_settings(ImageBackendKind.HF_LOCAL)
        backend = select_image_backend(s, has_reference=True)
        assert isinstance(backend, HFIPAdapterBackend)

    def test_hf_local_with_reference_img2img(self):
        from backends.hf_img2img import HFImg2ImgBackend
        from backends.registry import select_image_backend

        s = Settings(  # type: ignore[call-arg]
            _env_file=None,
            IMAGE_BACKEND_KIND=ImageBackendKind.HF_LOCAL,
            LOCAL_BACKEND="img2img",
        )
        backend = select_image_backend(s, has_reference=True)
        assert isinstance(backend, HFImg2ImgBackend)

    def test_hf_local_with_reference_hybrid(self):
        from backends.hf_hybrid import HFHybridBackend
        from backends.registry import select_image_backend

        s = Settings(  # type: ignore[call-arg]
            _env_file=None,
            IMAGE_BACKEND_KIND=ImageBackendKind.HF_LOCAL,
            LOCAL_BACKEND="hybrid",
        )
        backend = select_image_backend(s, has_reference=True)
        assert isinstance(backend, HFHybridBackend)


class TestSelectTextBackend:
    """텍스트 백엔드는 무조건 OpenAI (Stage 2 결정)."""

    def test_returns_openai_gpt_backend(self):
        from backends.openai_gpt import OpenAIGPTBackend
        from backends.registry import select_text_backend

        s = _make_settings(ImageBackendKind.MOCK)
        backend = select_text_backend(s)
        assert isinstance(backend, OpenAIGPTBackend)
