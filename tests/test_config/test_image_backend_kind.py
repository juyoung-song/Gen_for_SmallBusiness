"""ImageBackendKind enum + Settings 통합 테스트.

Stage 2 의 핵심 — 4가지 모드를 단일 enum 으로 표현:
- mock           — Pillow 그라데이션 (Mock)
- hf_local       — 같은 머신의 diffusers (개발자 또는 워커 GPU)
- hf_remote_api  — Hugging Face Serverless API
- remote_worker  — 자체 원격 워커 호출
"""

import pytest

from config.settings import ImageBackendKind, Settings


class TestImageBackendKind:
    def test_enum_has_exactly_four_values(self):
        assert len(list(ImageBackendKind)) == 4

    def test_enum_values_are_known_strings(self):
        assert ImageBackendKind.MOCK.value == "mock"
        assert ImageBackendKind.HF_LOCAL.value == "hf_local"
        assert ImageBackendKind.HF_REMOTE_API.value == "hf_remote_api"
        assert ImageBackendKind.REMOTE_WORKER.value == "remote_worker"

    def test_enum_can_be_constructed_from_string(self):
        assert ImageBackendKind("mock") is ImageBackendKind.MOCK
        assert ImageBackendKind("hf_local") is ImageBackendKind.HF_LOCAL
        assert ImageBackendKind("remote_worker") is ImageBackendKind.REMOTE_WORKER

    def test_enum_rejects_unknown_string(self):
        with pytest.raises(ValueError):
            ImageBackendKind("nonsense")


class TestSettingsImageBackendKind:
    def test_default_is_mock(self, monkeypatch):
        """기본값은 mock — 외부 의존 없이 처음 띄울 수 있어야 함."""
        # 환경변수가 영향 주지 않도록 비우기
        for var in ("IMAGE_BACKEND", "IMAGE_BACKEND_KIND", "USE_MOCK", "USE_LOCAL_MODEL"):
            monkeypatch.delenv(var, raising=False)
        # .env 파일 무시
        monkeypatch.setenv("PYDANTIC_SETTINGS_DISABLE_ENV_FILE", "1")

        s = Settings(_env_file=None)  # type: ignore[call-arg]
        assert s.IMAGE_BACKEND_KIND == ImageBackendKind.MOCK

    def test_env_var_string_is_parsed_to_enum(self, monkeypatch):
        monkeypatch.setenv("IMAGE_BACKEND_KIND", "hf_local")
        s = Settings(_env_file=None)  # type: ignore[call-arg]
        assert s.IMAGE_BACKEND_KIND == ImageBackendKind.HF_LOCAL

    def test_env_var_remote_worker(self, monkeypatch):
        monkeypatch.setenv("IMAGE_BACKEND_KIND", "remote_worker")
        s = Settings(_env_file=None)  # type: ignore[call-arg]
        assert s.IMAGE_BACKEND_KIND == ImageBackendKind.REMOTE_WORKER

    def test_invalid_env_var_raises(self, monkeypatch):
        monkeypatch.setenv("IMAGE_BACKEND_KIND", "garbage")
        with pytest.raises(Exception):  # ValidationError
            Settings(_env_file=None)  # type: ignore[call-arg]
