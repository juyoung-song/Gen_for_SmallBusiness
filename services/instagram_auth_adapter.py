"""기존 InstagramService와 신규 OAuth 연결을 이어주는 어댑터.

기존 코드를 수정하지 않고, settings 객체에 사용자별 토큰을 동적 주입합니다.
롤백 시 이 파일만 제거하면 기존 동작으로 원복됩니다.
"""

import logging

from config.settings import Settings
from utils.async_runner import run_async
from utils.crypto import decrypt_token

logger = logging.getLogger(__name__)


def apply_user_token(settings: Settings, brand_config) -> bool:
    """DB에서 사용자의 OAuth 토큰을 꺼내 settings에 주입.

    Args:
        settings: 앱 전역 설정 객체
        brand_config: 온보딩된 브랜드 설정 (None이면 미온보딩)

    Returns:
        True: 토큰이 준비됨 (업로드 가능)
        False: 연결 없음 (업로드 불가)
    """
    if not brand_config:
        return False

    from services.instagram_auth_service import InstagramAuthService

    auth_svc = InstagramAuthService(settings)
    conn = run_async(auth_svc.get_connection(brand_config.id))

    if not conn or not conn.is_active:
        # OAuth 연결이 없으면 기존 .env 토큰 사용 시도 (하위 호환)
        return bool(settings.META_ACCESS_TOKEN and settings.INSTAGRAM_ACCOUNT_ID)

    # DB 토큰을 복호화하여 settings에 동적 주입
    try:
        decrypted_token = decrypt_token(
            conn.access_token, settings.TOKEN_ENCRYPTION_KEY
        )
        settings.META_ACCESS_TOKEN = decrypted_token
        settings.INSTAGRAM_ACCOUNT_ID = conn.instagram_account_id
        logger.info(
            "사용자 OAuth 토큰 주입 완료 (ig_user=@%s)",
            conn.instagram_username,
        )
        return True
    except Exception as e:
        logger.error("토큰 복호화 실패: %s", e)
        return False
