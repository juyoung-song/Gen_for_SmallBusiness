"""기존 업로드 서비스와 OAuth 연결 정보를 이어주는 어댑터."""

from __future__ import annotations

import asyncio
import logging

from config.settings import Settings
from services.instagram_auth_service import InstagramAuthService

logger = logging.getLogger(__name__)


async def apply_user_token_async(settings: Settings, brand_image) -> bool:
    """브랜드별 OAuth 연결을 settings 객체에 주입한다.

    OAuth 연결이 없으면 기존 .env 기반 고정 계정 설정을 fallback 으로 사용한다.
    """

    if not brand_image:
        return False

    auth_service = InstagramAuthService(settings)
    connection = await auth_service.get_connection(brand_image.id)
    if not connection or not connection.is_active:
        return bool(settings.META_ACCESS_TOKEN and settings.INSTAGRAM_ACCOUNT_ID)

    try:
        settings.META_ACCESS_TOKEN = auth_service.decrypt_access_token(connection)
        settings.INSTAGRAM_ACCOUNT_ID = connection.instagram_account_id
        logger.info(
            "브랜드 OAuth 토큰 주입 완료 (ig_user=@%s)",
            connection.instagram_username,
        )
        return True
    except Exception as exc:  # pragma: no cover - runtime safety
        logger.error("인스타그램 토큰 복호화 실패: %s", exc)
        return False


def apply_user_token(settings: Settings, brand_image) -> bool:
    """동기 호출부(Streamlit 등) 호환용 래퍼."""

    try:
        return asyncio.get_event_loop().run_until_complete(
            apply_user_token_async(settings, brand_image)
        )
    except RuntimeError:
        return asyncio.run(apply_user_token_async(settings, brand_image))
