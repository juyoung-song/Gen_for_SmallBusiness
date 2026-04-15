"""Instagram OAuth 2.0 계정 연결 서비스.

Meta Graph API를 통해 사용자의 인스타그램 비즈니스 계정을
서비스에 연결하는 전체 OAuth 흐름을 처리합니다.

docs/schema.md §3.5 기준 재작성:
- `InstagramConnection` 은 토큰 전용. account_id/username 은 `Brand` 쪽에 저장.
- 저장 시 BrandService.link_instagram() 을 호출해 brand 에도 account_id 를 반영.
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Literal, Optional
from uuid import UUID

import httpx
from sqlalchemy import select

from config.database import AsyncSessionLocal
from config.settings import Settings
from models.instagram_connection import InstagramConnection
from services.brand_service import BrandService
from utils.crypto import encrypt_token

logger = logging.getLogger(__name__)


class InstagramPageConnectionRequiredError(ValueError):
    """Instagram professional account 와 Facebook Page 연결이 필요한 상태."""


class InstagramAuthService:
    """Meta OAuth를 통한 인스타그램 계정 연결/관리 서비스."""

    GRAPH_API_VERSION = "v19.0"
    BASE_URL = f"https://graph.facebook.com/{GRAPH_API_VERSION}"

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    # ── Step 1: OAuth URL 생성 ──

    def generate_oauth_url(
        self,
        state: str,
        *,
        surface: Literal["streamlit", "mobile"] = "mobile",
    ) -> str:
        """Meta OAuth 인증 시작 URL 생성."""
        from urllib.parse import quote

        redirect_uri = self.settings.get_meta_redirect_uri(surface)
        encoded_uri = quote(redirect_uri, safe="")
        return (
            f"https://www.facebook.com/{self.GRAPH_API_VERSION}/dialog/oauth"
            f"?client_id={self.settings.META_APP_ID}"
            f"&redirect_uri={encoded_uri}"
            f"&state={state}"
            f"&scope=instagram_basic,instagram_content_publish,"
            f"pages_show_list,pages_read_engagement"
        )

    # ── Step 2: code → Short-lived Token ──

    async def exchange_code_for_token(
        self,
        code: str,
        *,
        surface: Literal["streamlit", "mobile"] = "mobile",
    ) -> str:
        """Authorization code를 short-lived access token으로 교환."""
        redirect_uri = self.settings.get_meta_redirect_uri(surface)
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{self.BASE_URL}/oauth/access_token",
                params={
                    "client_id": self.settings.META_APP_ID,
                    "redirect_uri": redirect_uri,
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
        """연결된 Instagram Business Account 정보를 자동으로 조회.

        [명시적 가정]
        현재 구현은 사용자-페이지 당 IG 비즈니스 계정 1개 사용을 가정합니다.
        여러 계정이 발견되더라도 첫 번째 계정을 선택하여 반환합니다.
        (멀티 계정 선택 UI 확장은 추후 과제)
        """
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{self.BASE_URL}/me/accounts",
                params={
                    "fields": "id,name,access_token,instagram_business_account",
                    "access_token": access_token,
                },
            )
            resp.raise_for_status()

            resp_json = resp.json()
            if "data" not in resp_json:
                logger.error("Facebook 페이지 목록 응답에 'data' 필드가 없음: %s", resp_json)
                raise ValueError("Facebook 페이지 목록을 가져오는 데 실패했습니다 (data 필드 누락).")

            pages_data = resp_json.get("data", [])
            if not pages_data:
                raise InstagramPageConnectionRequiredError(
                    "Meta 로그인은 완료됐지만 접근 가능한 Facebook Page를 찾지 못했습니다. "
                    "Facebook에서 Page 권한을 확인하거나 새 Page를 만든 뒤 다시 시도해 주세요."
                )

            found_accounts = []

            for page in pages_data:
                p_id = page.get("id")
                p_name = page.get("name", "(이름 없는 페이지)")
                ig_info = page.get("instagram_business_account")
                if ig_info and "id" in ig_info:
                    found_accounts.append({
                        "facebook_page_id": p_id,
                        "facebook_page_name": p_name,
                        "instagram_account_id": ig_info["id"],
                    })

            if not found_accounts:
                raise InstagramPageConnectionRequiredError(
                    "Facebook Page는 확인됐지만 Instagram professional account가 연결되지 않았습니다. "
                    "Instagram 앱에서 프로필 편집 > 페이지에서 Facebook Page를 연결한 뒤 다시 시도해 주세요."
                )

            if len(found_accounts) > 1:
                logger.warning(
                    "여러 개의 Instagram 비즈니스 계정(%d개)이 발견되었습니다. "
                    "첫 번째 계정을 선택합니다. 목록: %s",
                    len(found_accounts), found_accounts,
                )

            selected = found_accounts[0]
            ig_id = selected["instagram_account_id"]
            p_name = selected["facebook_page_name"]
            p_id = selected["facebook_page_id"]

            usr_resp = await client.get(
                f"{self.BASE_URL}/{ig_id}",
                params={"fields": "username", "access_token": access_token},
            )

            if usr_resp.status_code != 200:
                logger.error("IG username 조회 실패 (HTTP %d): %s", usr_resp.status_code, usr_resp.text)
                raise ValueError(f"인스타그램 사용자명 조회 실패: {usr_resp.text}")

            username = usr_resp.json().get("username")
            if not username:
                logger.error("IG username 응답에 username 필드가 없습니다: %s", usr_resp.text)
                raise ValueError("인스타그램 응답에 사용자명(username)이 포함되어 있지 않습니다.")

            logger.info("Instagram 계정 최종 선택됨: @%s (via Facebook 페이지 '%s')", username, p_name)
            return {
                "instagram_account_id": ig_id,
                "instagram_username": username,
                "facebook_page_id": p_id,
                "facebook_page_name": p_name,
            }

    async def fetch_instagram_account_manually(
        self, access_token: str, instagram_id: str
    ) -> dict:
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
        self,
        brand_id: UUID,
        access_token: str,
        expires_in: int,
        ig_info: dict,
    ) -> InstagramConnection:
        """연결 정보(토큰 암호화 포함)를 DB에 저장.

        - `instagram_connections`: 토큰 + 만료 + facebook page 정보
        - `brands.instagram_account_id` / `instagram_username`: BrandService.link_instagram 호출
        """
        encrypted_token = encrypt_token(access_token, self.settings.TOKEN_ENCRYPTION_KEY)
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in)

        async with AsyncSessionLocal() as session:
            # 1) brand 에 instagram_account_id / username 반영
            brand_svc = BrandService(session)
            await brand_svc.link_instagram(
                brand_id,
                instagram_account_id=ig_info["instagram_account_id"],
                instagram_username=ig_info.get("instagram_username"),
            )

            # 2) instagram_connections 레코드 UPSERT (토큰 + facebook page)
            result = await session.execute(
                select(InstagramConnection).where(
                    InstagramConnection.brand_id == brand_id
                )
            )
            conn = result.scalar_one_or_none()

            if conn:
                conn.access_token = encrypted_token
                conn.token_expires_at = expires_at
                conn.facebook_page_id = ig_info.get("facebook_page_id")
                conn.facebook_page_name = ig_info.get("facebook_page_name")
                conn.is_active = True
            else:
                conn = InstagramConnection(
                    brand_id=brand_id,
                    access_token=encrypted_token,
                    token_type="long_lived",
                    token_expires_at=expires_at,
                    facebook_page_id=ig_info.get("facebook_page_id"),
                    facebook_page_name=ig_info.get("facebook_page_name"),
                    is_active=True,
                )
                session.add(conn)

            await session.commit()
            await session.refresh(conn)
            return conn

    # ── 조회 및 관리 ──

    async def get_connection(self, brand_id: UUID) -> Optional[InstagramConnection]:
        """활성 연결 상태 조회."""
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(InstagramConnection).where(
                    InstagramConnection.brand_id == brand_id,
                    InstagramConnection.is_active.is_(True),
                )
            )
            return result.scalar_one_or_none()

    async def revoke_connection(self, brand_id: UUID) -> None:
        """연결 비활성화."""
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(InstagramConnection).where(
                    InstagramConnection.brand_id == brand_id
                )
            )
            conn = result.scalar_one_or_none()
            if conn:
                conn.is_active = False
                await session.commit()
