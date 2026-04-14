"""앱 설정 — pydantic-settings 기반 환경 변수 로드.

Stage 2 (2026-04-09):
- 이전의 USE_MOCK / USE_LOCAL_MODEL / IMAGE_BACKEND 세 변수가 표현하던 4가지
  이미지 백엔드 모드를 단일 enum `IMAGE_BACKEND_KIND` 로 통합.
- 텍스트 백엔드는 무조건 OpenAI 가정 (Mock 분기는 caption_service 등에 살아있지만
  사용자가 토글로 켤 일은 없음 — 추후 정리 대상).
"""

import logging
from enum import Enum
from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class ImageBackendKind(str, Enum):
    """이미지 생성 백엔드 모드 (Stage 2).

    - mock           — Pillow 그라데이션 (개발/CI, 외부 의존 0)
    - hf_local       — 같은 머신의 diffusers (개발자 Mac 또는 워커 GPU)
    - hf_remote_api  — Hugging Face Serverless Inference API
    - remote_worker  — 자체 원격 워커 (worker_api.py) 호출
    """

    MOCK = "mock"
    HF_LOCAL = "hf_local"
    HF_REMOTE_API = "hf_remote_api"
    REMOTE_WORKER = "remote_worker"


class Settings(BaseSettings):
    """애플리케이션 전체 설정."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",  # 알 수 없는 변수가 .env 에 있어도 무시 (legacy 키 호환)
    )

    # ── AI API Keys ──
    OPENAI_API_KEY: str = ""
    HUGGINGFACE_API_KEY: str = ""

    # ── Instagram Upload Settings ──
    IMGBB_API_KEY: str = ""  # legacy, 코드에서 사용 안 함
    # C-1: FreeImage.host API 키 (기존 소스코드 하드코딩 제거).
    # .env 에 FREEIMAGE_API_KEY 를 설정하면 그 값을 사용. 미설정 시 공용 키로 폴백.
    FREEIMAGE_API_KEY: str = "6d207e02198a847aa98d0a2a901485a5"
    META_ACCESS_TOKEN: str = ""
    INSTAGRAM_ACCOUNT_ID: str = ""
    META_APP_ID: str = ""
    META_APP_SECRET: str = ""
    META_REDIRECT_URI: str = ""
    TOKEN_ENCRYPTION_KEY: str = ""

    # ── Instagram OAuth 2.0 (song 이식) ──
    # 신규 사용자가 OAuth 로 연결하는 경로. 미설정 시 위의 META_ACCESS_TOKEN /
    # INSTAGRAM_ACCOUNT_ID fallback 이 사용된다 (services/instagram_auth_adapter).
    META_APP_ID: str = ""
    META_APP_SECRET: str = ""
    META_REDIRECT_URI: str = "http://localhost:8501/"
    TOKEN_ENCRYPTION_KEY: str = ""  # Fernet 32-byte urlsafe base64; utils/crypto.generate_fernet_key()

    # ── Langfuse (LLM Observability) ──
    LANGFUSE_PUBLIC_KEY: str = ""
    LANGFUSE_SECRET_KEY: str = ""
    LANGFUSE_HOST: str = "https://cloud.langfuse.com"

    # ── Application ──
    APP_ENV: str = "development"
    LOG_LEVEL: str = "INFO"

    # ── 이미지 백엔드 모드 (Stage 2 단일 enum) ──
    IMAGE_BACKEND_KIND: ImageBackendKind = ImageBackendKind.MOCK

    # ── Model Settings ──
    # TEXT_MODEL: 텍스트 및 Vision 호출에 모두 사용.
    TEXT_MODEL: str = "gpt-5-mini"
    IMAGE_MODEL: str = "stabilityai/stable-diffusion-xl-base-1.0"
    IMAGE_SIZE: Literal["1024x1024", "1024x1792", "1792x1024"] = "1024x1024"
    IMAGE_QUALITY: Literal["standard", "hd"] = "standard"
    IMAGE_WORKER_URL: str = ""
    IMAGE_WORKER_TOKEN: str = ""
    IMAGE_WORKER_TIMEOUT: float = 180.0
    IMAGE_WORKER_HOST: str = "0.0.0.0"
    IMAGE_WORKER_PORT: int = 8005

    # ── API 요청 설정 ──
    TEXT_TIMEOUT: float = 90.0    # GPT 호출 타임아웃 (초)
    IMAGE_TIMEOUT: float = 90.0   # HF API 호출 타임아웃 (초)
    TEXT_TEMPERATURE: float = 0.8
    TEXT_MAX_TOKENS: int = 1000

    # ── 입력 제한 ──
    MAX_PRODUCT_NAME_LENGTH: int = 50
    MAX_DESCRIPTION_LENGTH: int = 200

    # ── 스토리 이미지 합성 (compose_story_image) ──
    # I-4: 폰트 경로를 macOS 하드코딩에서 분리. 콜론 구분 목록, 왼쪽부터 시도.
    STORY_FONT_PATHS: str = (
        "/System/Library/Fonts/Supplemental/AppleGothic.ttf:"
        "/usr/share/fonts/truetype/nanum/NanumGothic.ttf:"
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"
    )
    STORY_FONT_SIZE: int = 60

    # ── Local Model Settings (IMAGE_BACKEND_KIND=hf_local 시 사용) ──
    LOCAL_MODEL_CACHE_DIR: str = "./models/cache"
    LOCAL_SD15_MODEL_ID: str = "runwayml/stable-diffusion-v1-5"
    LOCAL_IP_ADAPTER_ID: str = "h94/IP-Adapter"
    LOCAL_IP_ADAPTER_SUBFOLDER: str = "models"
    LOCAL_IP_ADAPTER_WEIGHT_NAME: str = "ip-adapter_sd15.bin"
    LOCAL_INFERENCE_STEPS: int = 18
    LOCAL_GUIDANCE_SCALE: float = 7.5
    LOCAL_IP_ADAPTER_SCALE: float = 0.6    # 참조 이미지 반영 강도 (0.0~1.0)
    LOCAL_IMG2IMG_STRENGTH: float = 0.5    # img2img 노이즈 강도 (0=원본유지, 1=완전재생성)
    # 로컬 백엔드의 세부 모드: "ip_adapter" | "img2img" | "hybrid"
    # 참조 이미지 없을 때는 항상 sd15 (txt2img) 사용
    LOCAL_BACKEND: str = "ip_adapter"

    # ──────────────────────────────────────────
    # Convenience properties
    # ──────────────────────────────────────────
    @property
    def is_mock_image(self) -> bool:
        """이미지 백엔드가 Mock 모드인지 (외부 호출 전혀 안 함)."""
        return self.IMAGE_BACKEND_KIND == ImageBackendKind.MOCK

    @property
    def is_api_ready(self) -> bool:
        """OpenAI 텍스트/Vision 호출 가능 여부."""
        return (
            bool(self.OPENAI_API_KEY)
            and self.OPENAI_API_KEY != "sk-your-openai-api-key-here"
        )

    @property
    def is_huggingface_ready(self) -> bool:
        """Hugging Face API 준비 여부 (IMAGE_BACKEND_KIND=hf_remote_api 시 사용)."""
        return bool(self.HUGGINGFACE_API_KEY)

    @property
    def is_image_worker_ready(self) -> bool:
        """원격 이미지 워커 준비 여부 (IMAGE_BACKEND_KIND=remote_worker 시 사용)."""
        return bool(self.IMAGE_WORKER_URL and self.IMAGE_WORKER_TOKEN)

    @property
    def is_instagram_ready(self) -> bool:
        """인스타그램 업로드 준비 여부 (Meta Graph + FreeImage)."""
        return bool(
            self.META_ACCESS_TOKEN and self.INSTAGRAM_ACCOUNT_ID
        )

    @property
    def is_instagram_oauth_configured(self) -> bool:
        """개인 계정 OAuth 연결 기능을 켤 수 있는지 여부."""
        return bool(
            self.META_APP_ID
            and self.META_APP_SECRET
            and self.META_REDIRECT_URI
            and self.TOKEN_ENCRYPTION_KEY
        )


@lru_cache
def get_settings() -> Settings:
    """Settings 싱글턴 인스턴스 반환."""
    return Settings()


def setup_logging(settings: Settings) -> None:
    """애플리케이션 로깅 초기화."""
    logging.basicConfig(
        level=getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
