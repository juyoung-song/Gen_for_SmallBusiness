"""기존 InstagramService와 신규 OAuth 연결을 이어주는 어댑터.

docs/schema.md §3.5 기준:
- instagram_account_id / instagram_username 은 Brand 쪽에 저장.
- access_token 은 InstagramConnection 쪽에서 복호화해 settings 에 주입.
"""

import logging

from config.settings import Settings
from models.brand import Brand
from utils.async_runner import run_async
from utils.crypto import decrypt_token

logger = logging.getLogger(__name__)


def apply_user_token(settings: Settings, brand: Brand | None) -> bool:
    """DB에서 사용자의 OAuth 토큰을 꺼내 settings에 주입.

    Args:
        settings: 앱 전역 설정 객체
        brand: 온보딩된 Brand (None이면 미온보딩)

    Returns:
        True: 토큰이 준비됨 (업로드 가능)
        False: 연결 없음 (업로드 불가)
    """
    if brand is None:
        return False

    if not brand.instagram_account_id:
        # 온보딩은 했지만 인스타 연결은 아직 안 함 — .env 폴백
        return bool(settings.META_ACCESS_TOKEN and settings.INSTAGRAM_ACCOUNT_ID)

    from services.instagram_auth_service import InstagramAuthService

    auth_svc = InstagramAuthService(settings)
    conn = run_async(auth_svc.get_connection(brand.id))

    if not conn or not conn.is_active:
        return bool(settings.META_ACCESS_TOKEN and settings.INSTAGRAM_ACCOUNT_ID)

    try:
        decrypted_token = decrypt_token(conn.access_token, settings.TOKEN_ENCRYPTION_KEY)
    except Exception as e:
        # 복호화 실패는 대개 TOKEN_ENCRYPTION_KEY 불일치 / 손상된 토큰. silent False 는
        # "연결 필요" UX 로 귀결돼 진짜 원인을 숨김. 명시적으로 예외 전파.
        logger.exception("OAuth 토큰 복호화 실패 (brand_id=%s)", brand.id)
        raise RuntimeError(
            "OAuth 토큰 복호화에 실패했습니다. TOKEN_ENCRYPTION_KEY 가 "
            "초기 연결 시점과 동일한지 확인하세요. "
            f"(원인: {type(e).__name__}: {e})"
        ) from e

    settings.META_ACCESS_TOKEN = decrypted_token
    settings.INSTAGRAM_ACCOUNT_ID = brand.instagram_account_id
    logger.info(
        "사용자 OAuth 토큰 주입 완료 (ig_user=@%s)",
        brand.instagram_username,
    )
    return True
