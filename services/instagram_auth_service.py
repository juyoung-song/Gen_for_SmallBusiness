"""Meta OAuth 기반 인스타그램 계정 연결 서비스."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from urllib.parse import quote
from uuid import UUID

import httpx
from sqlalchemy import select

from config.database import AsyncSessionLocal
from config.settings import Settings
from models.instagram_connection import InstagramConnection
from utils.crypto import decrypt_token, encrypt_token

logger = logging.getLogger(__name__)


class InstagramAuthService:
    """Meta OAuth 토큰 발급과 연결 정보 관리를 담당한다."""

    GRAPH_API_VERSION = "v19.0"
    BASE_URL = f"https://graph.facebook.com/{GRAPH_API_VERSION}"

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def generate_oauth_url(self, state: str) -> str:
        encoded_uri = quote(self.settings.META_REDIRECT_URI, safe="")
        return (
            f"https://www.facebook.com/{self.GRAPH_API_VERSION}/dialog/oauth"
            f"?client_id={self.settings.META_APP_ID}"
            f"&redirect_uri={encoded_uri}"
            f"&state={state}"
            f"&scope=instagram_basic,instagram_content_publish,"
            f"pages_show_list,pages_read_engagement"
        )

    async def exchange_code_for_token(self, code: str) -> str:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                f"{self.BASE_URL}/oauth/access_token",
                params={
                    "client_id": self.settings.META_APP_ID,
                    "redirect_uri": self.settings.META_REDIRECT_URI,
                    "client_secret": self.settings.META_APP_SECRET,
                    "code": code,
                },
            )

        if response.is_error:
            detail = response.json().get("error", {})
            logger.error("Meta short-lived token 발급 실패: %s", detail)
            raise ValueError(
                detail.get("message", "Meta 인증 중 알 수 없는 오류가 발생했습니다.")
            )

        return response.json()["access_token"]

    async def exchange_for_long_lived_token(self, short_token: str) -> tuple[str, int]:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                f"{self.BASE_URL}/oauth/access_token",
                params={
                    "grant_type": "fb_exchange_token",
                    "client_id": self.settings.META_APP_ID,
                    "client_secret": self.settings.META_APP_SECRET,
                    "fb_exchange_token": short_token,
                },
            )

        if response.is_error:
            detail = response.json().get("error", {})
            logger.error("Meta long-lived token 발급 실패: %s", detail)
            raise ValueError(
                detail.get(
                    "message", "장기 인스타그램 토큰 발급 중 오류가 발생했습니다."
                )
            )

        payload = response.json()
        return payload["access_token"], payload.get("expires_in", 5_184_000)

    async def fetch_instagram_account(self, access_token: str) -> dict[str, str | None]:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                f"{self.BASE_URL}/me/accounts",
                params={
                    "fields": "id,name,access_token,instagram_business_account",
                    "access_token": access_token,
                },
            )

            if response.is_error:
                detail = response.json().get("error", {})
                raise ValueError(
                    detail.get(
                        "message",
                        "연결된 Facebook 페이지와 인스타그램 계정을 조회하지 못했습니다.",
                    )
                )

            for page in response.json().get("data", []):
                instagram_business_account = page.get("instagram_business_account")
                if not instagram_business_account:
                    continue

                instagram_account_id = instagram_business_account["id"]
                username_response = await client.get(
                    f"{self.BASE_URL}/{instagram_account_id}",
                    params={"fields": "username", "access_token": access_token},
                )
                username = username_response.json().get("username", "instagram_user")
                logger.info(
                    "인스타그램 계정 발견: @%s (page=%s)",
                    username,
                    page.get("name", "unknown"),
                )
                return {
                    "instagram_account_id": instagram_account_id,
                    "instagram_username": username,
                    "facebook_page_id": page["id"],
                    "facebook_page_name": page.get("name"),
                }

        raise ValueError(
            "연결된 Instagram 비즈니스 또는 크리에이터 계정을 자동으로 찾지 못했습니다."
        )

    async def save_connection(
        self,
        brand_image_id: UUID,
        access_token: str,
        expires_in: int,
        instagram_info: dict[str, str | None],
    ) -> InstagramConnection:
        encrypted_token = encrypt_token(access_token, self.settings.TOKEN_ENCRYPTION_KEY)
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in)

        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(InstagramConnection).where(
                    InstagramConnection.brand_image_id == brand_image_id
                )
            )
            connection = result.scalar_one_or_none()

            if connection is None:
                connection = InstagramConnection(
                    brand_image_id=brand_image_id,
                    access_token=encrypted_token,
                    token_type="long_lived",
                    token_expires_at=expires_at,
                    instagram_account_id=instagram_info["instagram_account_id"],
                    instagram_username=instagram_info.get("instagram_username"),
                    facebook_page_id=instagram_info.get("facebook_page_id"),
                    facebook_page_name=instagram_info.get("facebook_page_name"),
                    is_active=True,
                )
                session.add(connection)
            else:
                connection.access_token = encrypted_token
                connection.token_type = "long_lived"
                connection.token_expires_at = expires_at
                connection.instagram_account_id = instagram_info["instagram_account_id"]
                connection.instagram_username = instagram_info.get("instagram_username")
                connection.facebook_page_id = instagram_info.get("facebook_page_id")
                connection.facebook_page_name = instagram_info.get("facebook_page_name")
                connection.is_active = True

            await session.commit()
            await session.refresh(connection)
            return connection

    async def get_connection(self, brand_image_id: UUID) -> InstagramConnection | None:
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(InstagramConnection).where(
                    InstagramConnection.brand_image_id == brand_image_id,
                    InstagramConnection.is_active.is_(True),
                )
            )
            return result.scalar_one_or_none()

    async def revoke_connection(self, brand_image_id: UUID) -> None:
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(InstagramConnection).where(
                    InstagramConnection.brand_image_id == brand_image_id
                )
            )
            connection = result.scalar_one_or_none()
            if connection is not None:
                connection.is_active = False
                await session.commit()

    def decrypt_access_token(self, connection: InstagramConnection) -> str:
        return decrypt_token(connection.access_token, self.settings.TOKEN_ENCRYPTION_KEY)
