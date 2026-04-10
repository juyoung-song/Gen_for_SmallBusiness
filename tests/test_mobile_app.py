"""mobile_app 엔드포인트 보조 로직 테스트."""

from __future__ import annotations

import httpx
import pytest
from fastapi import HTTPException
from openai import APITimeoutError
from types import SimpleNamespace
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import mobile_app
from schemas.instagram_schema import CaptionGenerationResponse


class TestDownloadReferenceImage:
    async def test_rejects_non_http_scheme(self):
        with pytest.raises(HTTPException) as exc_info:
            await mobile_app._download_reference_image("ftp://example.com/image.png")

        assert exc_info.value.status_code == 400
        assert "http://" in exc_info.value.detail

    async def test_rejects_non_image_content_type(self, monkeypatch):
        response = httpx.Response(
            200,
            headers={"content-type": "text/html; charset=utf-8"},
            content=b"<html></html>",
            request=httpx.Request("GET", "https://example.com/page"),
        )

        class DummyClient:
            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc, tb):
                return False

            async def get(self, _):
                return response

        monkeypatch.setattr(mobile_app.httpx, "AsyncClient", lambda **_: DummyClient())

        with pytest.raises(HTTPException) as exc_info:
            await mobile_app._download_reference_image("https://example.com/page")

        assert exc_info.value.status_code == 400
        assert "이미지" in exc_info.value.detail


class TestMobileCaption:
    async def test_translates_timeout_error_to_http_exception(self, monkeypatch):
        async def fake_load_brand_prompt():
            return "브랜드 프롬프트"

        def fake_generate_caption(self, request):
            raise APITimeoutError(
                request=httpx.Request("POST", "https://api.openai.com/v1/chat/completions")
            )

        monkeypatch.setattr(mobile_app, "_load_brand_prompt", fake_load_brand_prompt)
        monkeypatch.setattr(
            mobile_app.CaptionService,
            "generate_caption",
            fake_generate_caption,
        )

        with pytest.raises(HTTPException) as exc_info:
            await mobile_app.mobile_caption(
                mobile_app.MobileCaptionRequest(
                    product_name="시그니처 식빵",
                    ad_copies=["겉은 바삭하고 속은 촉촉한 하루"],
                )
            )

        assert exc_info.value.status_code == 504
        assert "초과" in exc_info.value.detail

    async def test_returns_caption_response_when_service_succeeds(self, monkeypatch):
        async def fake_load_brand_prompt():
            return "브랜드 프롬프트"

        def fake_generate_caption(self, request):
            return CaptionGenerationResponse(
                caption="따뜻한 식감이 오래 남는 식빵 한 장",
                hashtags="#식빵 #베이커리",
            )

        monkeypatch.setattr(mobile_app, "_load_brand_prompt", fake_load_brand_prompt)
        monkeypatch.setattr(
            mobile_app.CaptionService,
            "generate_caption",
            fake_generate_caption,
        )

        response = await mobile_app.mobile_caption(
            mobile_app.MobileCaptionRequest(
                product_name="시그니처 식빵",
                ad_copies=["겉은 바삭하고 속은 촉촉한 하루"],
            )
        )

        assert response.caption == "따뜻한 식감이 오래 남는 식빵 한 장"
        assert response.hashtags == "#식빵 #베이커리"


class TestInstagramSummary:
    async def test_reports_connected_oauth_account(self, monkeypatch):
        brand = SimpleNamespace(id=uuid4())
        future_expiry = datetime.now(timezone.utc) + timedelta(days=30)

        async def fake_get_connection(self, _brand_id):
            return SimpleNamespace(
                is_active=True,
                instagram_username="bakery_owner",
                facebook_page_name="Bakery Page",
                token_expires_at=future_expiry,
            )

        monkeypatch.setattr(mobile_app.settings, "META_APP_ID", "app-id")
        monkeypatch.setattr(mobile_app.settings, "META_APP_SECRET", "secret")
        monkeypatch.setattr(mobile_app.settings, "META_REDIRECT_URI", "https://example.com/callback")
        monkeypatch.setattr(mobile_app.settings, "TOKEN_ENCRYPTION_KEY", "token-key")
        monkeypatch.setattr(
            mobile_app.InstagramAuthService,
            "get_connection",
            fake_get_connection,
        )

        summary = await mobile_app._load_instagram_summary(brand)

        assert summary.connected is True
        assert summary.upload_ready is True
        assert summary.connection_source == "oauth"
        assert summary.username == "bakery_owner"

    async def test_falls_back_to_env_upload_state(self, monkeypatch):
        async def fake_get_connection(self, _brand_id):
            return None

        monkeypatch.setattr(mobile_app.settings, "META_ACCESS_TOKEN", "fallback-token")
        monkeypatch.setattr(mobile_app.settings, "INSTAGRAM_ACCOUNT_ID", "1784")
        monkeypatch.setattr(mobile_app.settings, "META_APP_ID", "")
        monkeypatch.setattr(mobile_app.settings, "META_APP_SECRET", "")
        monkeypatch.setattr(mobile_app.settings, "META_REDIRECT_URI", "")
        monkeypatch.setattr(mobile_app.settings, "TOKEN_ENCRYPTION_KEY", "")
        monkeypatch.setattr(
            mobile_app.InstagramAuthService,
            "get_connection",
            fake_get_connection,
        )

        summary = await mobile_app._load_instagram_summary(None)

        assert summary.connected is False
        assert summary.upload_ready is True
        assert summary.connection_source == "env"


class TestInstagramOnboardingFlow:
    async def test_connect_url_accepts_onboarding_source(self, monkeypatch):
        brand_id = uuid4()

        async def fake_load_brand():
            return SimpleNamespace(id=brand_id)

        monkeypatch.setattr(mobile_app, "_load_brand", fake_load_brand)
        monkeypatch.setattr(mobile_app.settings, "META_APP_ID", "meta-app")
        monkeypatch.setattr(mobile_app.settings, "META_APP_SECRET", "meta-secret")
        monkeypatch.setattr(
            mobile_app.settings,
            "META_REDIRECT_URI",
            "https://example.com/api/mobile/instagram/callback",
        )
        monkeypatch.setattr(mobile_app.settings, "TOKEN_ENCRYPTION_KEY", "token-key")
        monkeypatch.setattr(
            mobile_app.InstagramAuthService,
            "generate_oauth_url",
            lambda self, state: f"https://meta.example/oauth?state={state}",
        )

        response = await mobile_app.mobile_instagram_connect_url(
            mobile_app.MobileInstagramConnectRequest(source="onboarding")
        )

        state = response.url.split("state=", 1)[1]
        pending_brand_id, pending_source, _ = mobile_app.PENDING_INSTAGRAM_STATES[state]
        assert pending_brand_id == brand_id
        assert pending_source == "onboarding"

    async def test_callback_redirects_back_to_onboarding_page(self):
        state = mobile_app._issue_instagram_state(uuid4(), "onboarding")

        response = await mobile_app.mobile_instagram_callback(
            state=state,
            error="access_denied",
        )

        assert response.headers["location"].startswith(
            "/stitch/onboarding-instagram.html?ig=cancelled"
        )


class TestRootRedirect:
    async def test_redirects_to_welcome_when_onboarding_incomplete(self, monkeypatch):
        async def fake_load_brand():
            return None

        monkeypatch.setattr(mobile_app, "_load_brand", fake_load_brand)

        response = await mobile_app.root()

        assert response.headers["location"] == "/stitch/welcome.html"

    async def test_redirects_to_home_when_brand_exists(self, monkeypatch):
        async def fake_load_brand():
            return SimpleNamespace(id=uuid4())

        monkeypatch.setattr(mobile_app, "_load_brand", fake_load_brand)

        response = await mobile_app.root()

        assert response.headers["location"] == "/stitch/index.html"
