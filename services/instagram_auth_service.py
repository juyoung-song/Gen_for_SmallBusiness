"""Instagram OAuth 2.0 계정 연결 서비스.

Meta Graph API를 통해 사용자의 인스타그램 비즈니스 계정을
서비스에 연결하는 전체 OAuth 흐름을 처리합니다.
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional
from uuid import UUID

import httpx
from sqlalchemy import select

from config.database import AsyncSessionLocal
from config.settings import Settings
from models.instagram_connection import InstagramConnection
from utils.crypto import decrypt_token, encrypt_token

logger = logging.getLogger(__name__)


class InstagramAuthService:
    """Meta OAuth를 통한 인스타그램 계정 연결/관리 서비스."""

    GRAPH_API_VERSION = "v19.0"
    BASE_URL = f"https://graph.facebook.com/{GRAPH_API_VERSION}"

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    # ── Step 1: OAuth URL 생성 ──

    def generate_oauth_url(self, state: str) -> str:
        """Meta OAuth 인증 시작 URL 생성."""
        from urllib.parse import quote
        
        encoded_uri = quote(self.settings.META_REDIRECT_URI, safe="")
        return (
            f"https://www.facebook.com/{self.GRAPH_API_VERSION}/dialog/oauth"
            f"?client_id={self.settings.META_APP_ID}"
            f"&redirect_uri={encoded_uri}"
            f"&state={state}"
            f"&scope=instagram_basic,instagram_content_publish,"
            f"pages_show_list,pages_read_engagement"
        )

    # ── Step 2: code → Short-lived Token ──

    async def exchange_code_for_token(self, code: str) -> str:
        """Authorization code를 short-lived access token으로 교환."""
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{self.BASE_URL}/oauth/access_token",
                params={
                    "client_id": self.settings.META_APP_ID,
                    "redirect_uri": self.settings.META_REDIRECT_URI,
                    "client_secret": self.settings.META_APP_SECRET,
                    "code": code,
                },
            )
            
            if resp.is_error:
                error_detail = resp.json().get("error", {})
                logger.error("Meta Token Exchange 실패: %s", error_detail)
                raise ValueError(f"Meta 인증 실패: {error_detail.get('message', '알 수 없는 에러')}")

            data = resp.json()
            logger.info("Short-lived token 발급 성공")
            return data["access_token"]

    # ── Step 3: Short-lived → Long-lived Token (60일) ──

    async def exchange_for_long_lived_token(self, short_token: str) -> tuple[str, int]:
        """Short-lived token을 60일짜리 long-lived token으로 교환."""
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{self.BASE_URL}/oauth/access_token",
                params={
                    "grant_type": "fb_exchange_token",
                    "client_id": self.settings.META_APP_ID,
                    "client_secret": self.settings.META_APP_SECRET,
                    "fb_exchange_token": short_token,
                },
            )
            resp.raise_for_status()
            data = resp.json()
            expires_in = data.get("expires_in", 5184000)
            logger.info("Long-lived token 발급 성공")
            return data["access_token"], expires_in

    # ── Step 4: Instagram Business Account 조회 ──

    async def fetch_instagram_account(self, access_token: str) -> dict:
        """연결된 Instagram Business Account 정보를 자동으로 조회."""
        async with httpx.AsyncClient() as client:
            # 1) 사용자의 페이지 목록 조회 (직접적인 fields 쿼리 사용)
            resp = await client.get(
                f"{self.BASE_URL}/me/accounts",
                params={
                    "fields": "id,name,access_token,instagram_business_account",
                    "access_token": access_token
                }
            )
            resp.raise_for_status()
            pages_data = resp.json().get("data", [])

            # 2) 모든 페이지를 순회하며 인스타그램 연결 확인
            for page in pages_data:
                p_id = page["id"]
                p_name = page.get("name", "알 수 없음")
                ig_info = page.get("instagram_business_account")
                
                if ig_info:
                    ig_id = ig_info["id"]
                    # 인스타그램 username 추가 조회
                    usr_resp = await client.get(
                        f"{self.BASE_URL}/{ig_id}",
                        params={"fields": "username", "access_token": access_token}
                    )
                    username = usr_resp.json().get("username", "instagram_user")
                    
                    logger.info("Instagram 계정 발견: @%s (via %s)", username, p_name)
                    return {
                        "instagram_account_id": ig_id,
                        "instagram_username": username,
                        "facebook_page_id": p_id,
                        "facebook_page_name": p_name,
                    }

            # 아무것도 못 찾은 경우 UI에서 수동 입력을 유도하기 위해 에러 발생
            raise ValueError("연결된 Instagram 비즈니스 계정을 자동으로 찾을 수 없습니다. 수동 연결을 이용해 주세요.")

    async def fetch_instagram_account_manually(self, access_token: str, instagram_id: str) -> dict:
        """입력받은 ID를 통해 인스타그램 계정 정보를 직접 확인."""
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{self.BASE_URL}/{instagram_id}",
                params={"fields": "username,id,name", "access_token": access_token},
            )
            
            if resp.is_error:
                raise ValueError("입력하신 인스타그램 ID가 유효하지 않거나 권한이 없습니다.")
                
            data = resp.json()
            return {
                "instagram_account_id": instagram_id,
                "instagram_username": data.get("username", "알 수 없음"),
                "facebook_page_id": None,
                "facebook_page_name": "수동 연결",
            }

    # ── Step 5: DB 저장 ──

    async def save_connection(
        self, brand_config_id: UUID, access_token: str, expires_in: int, ig_info: dict
    ) -> InstagramConnection:
        """연결 정보(토큰 암호화 포함)를 DB에 저장."""
        encrypted_token = encrypt_token(access_token, self.settings.TOKEN_ENCRYPTION_KEY)
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in)

        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(InstagramConnection).where(InstagramConnection.brand_config_id == brand_config_id)
            )
            conn = result.scalar_one_or_none()

            if conn:
                conn.access_token = encrypted_token
                conn.token_expires_at = expires_at
                conn.instagram_account_id = ig_info["instagram_account_id"]
                conn.instagram_username = ig_info.get("instagram_username")
                conn.is_active = True
            else:
                conn = InstagramConnection(
                    brand_config_id=brand_config_id,
                    access_token=encrypted_token,
                    token_type="long_lived",
                    token_expires_at=expires_at,
                    instagram_account_id=ig_info["instagram_account_id"],
                    instagram_username=ig_info.get("instagram_username"),
                    facebook_page_id=ig_info.get("facebook_page_id"),
                    facebook_page_name=ig_info.get("facebook_page_name"),
                    is_active=True,
                )
                session.add(conn)

            await session.commit()
            return conn

    # ── 조회 및 관리 ──

    async def get_connection(self, brand_config_id: UUID) -> Optional[InstagramConnection]:
        """활성 연결 상태 조회."""
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(InstagramConnection).where(
                    InstagramConnection.brand_config_id == brand_config_id,
                    InstagramConnection.is_active == True,
                )
            )
            return result.scalar_one_or_none()

    async def revoke_connection(self, brand_config_id: UUID) -> None:
        """연결 비활성화."""
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(InstagramConnection).where(InstagramConnection.brand_config_id == brand_config_id)
            )
            conn = result.scalar_one_or_none()
            if conn:
                conn.is_active = False
                await session.commit()
