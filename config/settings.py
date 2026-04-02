"""앱 설정 — pydantic-settings 기반 환경 변수 로드.

architecture.md 4.5 기준:
- .env 파일에서 환경 변수 로드
- 타입 안전한 설정값 제공
- API 모드 전환 시 키 유효성 검증
"""

import logging
from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """애플리케이션 전체 설정."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",  # 추가 필드(예: 기존 IMGBB_API_KEY)가 있어도 무시하고 실행
    )

    # ── AI API Keys ──
    OPENAI_API_KEY: str = ""
    HUGGINGFACE_API_KEY: str = ""

    # ── Instagram Upload Settings ──
    FREEIMAGE_API_KEY: str = ""
    META_ACCESS_TOKEN: str = ""
    INSTAGRAM_ACCOUNT_ID: str = ""

    # ── Application ──
    APP_ENV: str = "development"
    LOG_LEVEL: str = "INFO"
    USE_MOCK: bool = True

    # ── Model Settings ──
    TEXT_MODEL: str = "gpt-5-mini"
    IMAGE_MODEL: str = "stabilityai/stable-diffusion-xl-base-1.0"
    IMAGE_SIZE: Literal["1024x1024", "1024x1792", "1792x1024"] = "1024x1024"
    IMAGE_QUALITY: Literal["standard", "hd"] = "standard"

    # ── API 요청 설정 ──
    TEXT_TIMEOUT: float = 30.0    # GPT 호출 타임아웃 (초)
    IMAGE_TIMEOUT: float = 60.0   # DALL-E 호출 타임아웃 (초)
    TEXT_TEMPERATURE: float = 0.8  # 텍스트 생성 온도
    TEXT_MAX_TOKENS: int = 1000    # 텍스트 최대 토큰

    # ── 입력 제한 ──
    MAX_PRODUCT_NAME_LENGTH: int = 50
    MAX_DESCRIPTION_LENGTH: int = 200

    @property
    def is_api_ready(self) -> bool:
        """API 모드 사용 가능 여부 확인.

        USE_MOCK=false이고 OPENAI_API_KEY가 유효할 때만 True.
        """
        return (
            not self.USE_MOCK
            and bool(self.OPENAI_API_KEY)
            and self.OPENAI_API_KEY != "sk-your-openai-api-key-here"
        )

    @property
    def is_huggingface_ready(self) -> bool:
        """Hugging Face API 준비 여부"""
        return (
            not self.USE_MOCK
            and bool(self.HUGGINGFACE_API_KEY)
        )

    @property
    def is_instagram_ready(self) -> bool:
        """인스타그램 업로드(Meta API & ImgBB API) 준비 여부"""
        return bool(
            self.IMGBB_API_KEY and self.META_ACCESS_TOKEN and self.INSTAGRAM_ACCOUNT_ID
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
