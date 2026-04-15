"""mobile_app 엔드포인트 보조 로직 테스트."""

from __future__ import annotations

from contextlib import nullcontext
from datetime import datetime, timedelta, timezone
import httpx
import pytest
from fastapi import HTTPException
from openai import APITimeoutError
from types import SimpleNamespace
from uuid import uuid4

import mobile_app
from schemas.image_schema import ImageGenerationResponse
from schemas.instagram_schema import CaptionGenerationResponse
from schemas.text_schema import TextGenerationResponse
from services.generation_service import GenerationService
from services.instagram_auth_service import InstagramPageConnectionRequiredError


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


class TestMobileGenerate:
    async def test_passes_langfuse_trace_id_to_generation_save(self, monkeypatch):
        brand = SimpleNamespace(
            id=uuid4(),
            name="구름 베이커리",
            color_hex="#ff7448",
            style_prompt="따뜻한 브랜드 가이드",
            logo_path=None,
        )
        captured: dict = {}

        async def fake_load_brand():
            return brand

        async def fake_run_in_threadpool(func, *args, **kwargs):
            return func(*args, **kwargs)

        async def fake_save_generation_outputs(**kwargs):
            captured.update(kwargs)
            return uuid4(), uuid4()

        def fake_generate_ad_copy(self, request):
            return TextGenerationResponse(
                ad_copies=["따뜻한 아침을 여는 소금빵"],
                promo_sentences=["한 입 베어 물면 하루가 부드럽게 시작돼요."],
                story_copies=["오늘의 첫 빵"],
            )

        def fake_generate_ad_image(self, request):
            return ImageGenerationResponse(
                image_data=b"fake-image",
                revised_prompt="warm bakery prompt",
            )

        monkeypatch.setattr(mobile_app, "_load_brand", fake_load_brand)
        monkeypatch.setattr(mobile_app, "run_in_threadpool", fake_run_in_threadpool)
        monkeypatch.setattr(
            mobile_app,
            "_save_generation_outputs",
            fake_save_generation_outputs,
        )
        monkeypatch.setattr(
            mobile_app.TextService,
            "generate_ad_copy",
            fake_generate_ad_copy,
        )
        monkeypatch.setattr(
            mobile_app.ImageService,
            "generate_ad_image",
            fake_generate_ad_image,
        )
        monkeypatch.setattr(mobile_app, "_langfuse_trace_span", lambda _name: nullcontext())
        monkeypatch.setattr(
            mobile_app,
            "_capture_langfuse_trace_id",
            lambda: "trace-mobile-123",
        )

        await mobile_app.mobile_generate(
            mobile_app.MobileGenerateRequest(
                product_name="소금빵",
                description="겉은 바삭하고 속은 촉촉한 대표 메뉴",
                generation_type="both",
            )
        )

        assert captured["langfuse_trace_id"] == "trace-mobile-123"

    async def test_save_generation_outputs_persists_langfuse_trace_id(
        self,
        monkeypatch,
        db_session,
        brand_factory,
    ):
        brand = await brand_factory()

        class DummySessionContext:
            async def __aenter__(self):
                return db_session

            async def __aexit__(self, exc_type, exc, tb):
                return False

        monkeypatch.setattr(
            mobile_app,
            "AsyncSessionLocal",
            lambda: DummySessionContext(),
        )

        generation_id, _ = await mobile_app._save_generation_outputs(
            brand=brand,
            product_name="소금빵",
            description="버터 풍미가 진한 대표 메뉴",
            goal="일반 홍보",
            tone="기본",
            text_result={
                "ad_copies": ["따뜻한 소금빵"],
                "promo_sentences": ["오늘 가장 먼저 집어 들게 되는 빵"],
                "story_copies": ["갓 구운 소금빵"],
            },
            image_bytes=None,
            langfuse_trace_id="trace-mobile-abc",
        )

        saved = await GenerationService(db_session).get_with_outputs(generation_id)

        assert saved is not None
        assert saved.langfuse_trace_id == "trace-mobile-abc"


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
        monkeypatch.setattr(
            mobile_app.settings,
            "META_REDIRECT_URI_MOBILE",
            "https://example.com/callback",
        )
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
        monkeypatch.setattr(mobile_app.settings, "META_REDIRECT_URI_MOBILE", "")
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
    async def test_connect_url_returns_placeholder_when_oauth_not_configured(
        self, monkeypatch
    ):
        async def fake_load_brand():
            return SimpleNamespace(id=uuid4())

        monkeypatch.setattr(mobile_app, "_load_brand", fake_load_brand)
        monkeypatch.setattr(mobile_app.settings, "META_APP_ID", "")
        monkeypatch.setattr(mobile_app.settings, "META_APP_SECRET", "")
        monkeypatch.setattr(mobile_app.settings, "META_REDIRECT_URI", "")
        monkeypatch.setattr(mobile_app.settings, "META_REDIRECT_URI_MOBILE", "")
        monkeypatch.setattr(mobile_app.settings, "TOKEN_ENCRYPTION_KEY", "")

        response = await mobile_app.mobile_instagram_connect_url(
            mobile_app.MobileInstagramConnectRequest(source="settings")
        )

        assert response.mode == "placeholder"
        assert response.url is None
        assert "Meta" in (response.message or "")

    async def test_connect_url_accepts_onboarding_source(self, monkeypatch):
        brand_id = uuid4()

        async def fake_load_brand():
            return SimpleNamespace(id=brand_id)

        monkeypatch.setattr(mobile_app, "_load_brand", fake_load_brand)
        monkeypatch.setattr(mobile_app.settings, "META_APP_ID", "meta-app")
        monkeypatch.setattr(mobile_app.settings, "META_APP_SECRET", "meta-secret")
        monkeypatch.setattr(
            mobile_app.settings,
            "META_REDIRECT_URI_MOBILE",
            "https://example.com/api/mobile/instagram/callback",
        )
        monkeypatch.setattr(mobile_app.settings, "TOKEN_ENCRYPTION_KEY", "token-key")
        monkeypatch.setattr(
            mobile_app.InstagramAuthService,
            "generate_oauth_url",
            lambda self, state, **_: f"https://meta.example/oauth?state={state}",
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

    async def test_callback_redirects_with_page_required_feedback(self, monkeypatch):
        state = mobile_app._issue_instagram_state(uuid4(), "settings")

        async def fake_exchange_code_for_token(self, _code, **_kwargs):
            return "short-token"

        async def fake_exchange_for_long_lived_token(self, _short_token):
            return "long-token", 3600

        async def fake_fetch_instagram_account(self, _access_token):
            raise InstagramPageConnectionRequiredError(
                "Facebook Page 연결이 필요합니다."
            )

        monkeypatch.setattr(
            mobile_app.InstagramAuthService,
            "exchange_code_for_token",
            fake_exchange_code_for_token,
        )
        monkeypatch.setattr(
            mobile_app.InstagramAuthService,
            "exchange_for_long_lived_token",
            fake_exchange_for_long_lived_token,
        )
        monkeypatch.setattr(
            mobile_app.InstagramAuthService,
            "fetch_instagram_account",
            fake_fetch_instagram_account,
        )

        response = await mobile_app.mobile_instagram_callback(
            code="oauth-code",
            state=state,
        )

        assert response.headers["location"].startswith(
            "/stitch/settings.html?ig=page_required"
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


class TestMobileUploads:
    async def test_feed_upload_requires_connected_account(self, monkeypatch):
        async def fake_load_brand():
            return SimpleNamespace(id=uuid4())

        async def fake_apply_user_token_async(_settings, _brand):
            return False

        monkeypatch.setattr(mobile_app, "_load_brand", fake_load_brand)
        monkeypatch.setattr(
            mobile_app,
            "apply_user_token_async",
            fake_apply_user_token_async,
        )

        with pytest.raises(HTTPException) as exc_info:
            await mobile_app.mobile_upload_feed(
                mobile_app.MobileFeedUploadRequest(
                    product_name="소금빵",
                    caption="따끈한 소금빵 나왔어요",
                    image_data_url="data:image/png;base64,ZmFrZQ==",
                )
            )

        assert exc_info.value.status_code == 409
        assert "연결" in exc_info.value.detail

    async def test_feed_upload_returns_post_metadata(self, monkeypatch):
        brand = SimpleNamespace(id=uuid4())
        upload_id = uuid4()
        generation_output_id = uuid4()
        posted_at = datetime.now(timezone.utc)

        async def fake_load_brand():
            return brand

        async def fake_apply_user_token_async(_settings, _brand):
            return True

        async def fake_load_instagram_summary(_brand):
            return mobile_app.MobileInstagramSummary(
                oauth_available=True,
                connected=True,
                upload_ready=True,
                connection_source="oauth",
                username="bakery_owner",
            )

        async def fake_run_in_threadpool(func, *args, **kwargs):
            return func(*args, **kwargs)

        class DummyInstagramService:
            def __init__(self, _settings):
                self.last_post_id = None
                self.last_posted_at = None

            def upload_real(self, _image_bytes, _caption):
                self.last_post_id = "17841234567890"
                self.last_posted_at = posted_at
                yield "DONE"

            def upload_story(self, _image_bytes, _caption):
                self.last_post_id = "17841234567890"
                self.last_posted_at = posted_at
                yield "DONE"

        class DummyUploadService:
            def __init__(self, _session):
                pass

            async def create(self, **_kwargs):
                return SimpleNamespace(id=upload_id)

            async def mark_posted(self, **_kwargs):
                return None

        class DummySessionContext:
            async def __aenter__(self):
                return object()

            async def __aexit__(self, exc_type, exc, tb):
                return False

        monkeypatch.setattr(mobile_app, "_load_brand", fake_load_brand)
        monkeypatch.setattr(
            mobile_app,
            "apply_user_token_async",
            fake_apply_user_token_async,
        )
        monkeypatch.setattr(
            mobile_app,
            "_load_instagram_summary",
            fake_load_instagram_summary,
        )
        monkeypatch.setattr(mobile_app, "run_in_threadpool", fake_run_in_threadpool)
        monkeypatch.setattr(mobile_app, "InstagramService", DummyInstagramService)
        monkeypatch.setattr(mobile_app, "UploadService", DummyUploadService)
        monkeypatch.setattr(mobile_app, "AsyncSessionLocal", lambda: DummySessionContext())

        response = await mobile_app.mobile_upload_feed(
            mobile_app.MobileFeedUploadRequest(
                product_name="소금빵",
                description="버터 풍미가 진한 대표 메뉴",
                goal="신제품 출시",
                caption="따끈한 소금빵 나왔어요",
                image_data_url="data:image/png;base64,ZmFrZQ==",
                generation_output_id=generation_output_id,
            )
        )

        assert response.status == "ok"
        assert response.kind == "feed"
        assert response.instagram_post_id == "17841234567890"
        assert response.generated_upload_id == upload_id
        assert response.account_username == "bakery_owner"


# ─────────────────────────────────────────────────────────────
# CP17 — 백엔드 기능 보존 통합 (logo_service + reference_service)
# ─────────────────────────────────────────────────────────────
class TestCP17OnboardingAutoLogo:
    """payload.logo 가 None 이면 LogoAutoGenerator 로 자동 생성되어야 한다.

    Streamlit 의 `OnboardingService.finalize` 가 보장하던 동작을 mobile 에서도 동일하게.
    """

    async def test_complete_onboarding_auto_generates_logo_when_missing(
        self, monkeypatch, tmp_path
    ):
        # 기존 brand 가 없는 상태로 만든다 (get_first → None)
        async def fake_get_first(self):
            return None

        monkeypatch.setattr(mobile_app.BrandService, "get_first", fake_get_first)

        # 인스타 캡처는 하지 않게 (instagram_url 비움)
        # Vision 분석은 settings.is_api_ready 가 False 라 자동으로 skip 됨
        monkeypatch.setattr(
            type(mobile_app.settings), "is_api_ready",
            property(lambda self: False),
        )

        # LogoAutoGenerator 호출 추적용 spy
        captured: dict = {}

        original_init = mobile_app.LogoAutoGenerator.__init__
        original_gen = mobile_app.LogoAutoGenerator.generate_and_save

        def fake_generate_and_save(self, *, name, color_hex):
            captured["name"] = name
            captured["color_hex"] = color_hex
            path = tmp_path / f"{name}.png"
            path.write_bytes(b"\x89PNG_FAKE_AUTO_LOGO")
            return path

        monkeypatch.setattr(
            mobile_app.LogoAutoGenerator,
            "generate_and_save",
            fake_generate_and_save,
        )

        # BrandService.create 도 spy — 어떤 logo_path 가 들어가는지 확인
        async def fake_create(self, **kwargs):
            captured["create_kwargs"] = kwargs
            return SimpleNamespace(
                id=uuid4(),
                name=kwargs["name"],
                color_hex=kwargs["color_hex"],
                input_mood=kwargs.get("input_mood", ""),
                logo_path=kwargs.get("logo_path"),
                style_prompt=kwargs.get("style_prompt", ""),
            )

        monkeypatch.setattr(mobile_app.BrandService, "create", fake_create)

        response = await mobile_app.complete_onboarding(
            mobile_app.MobileOnboardingRequest(
                brand_name="구름",
                brand_color="#5562EA",
                brand_atmosphere="따뜻한",
                freetext="베이커리 카페",
                instagram_url="",
                logo=None,
            )
        )

        # LogoAutoGenerator 가 호출됐고, 그 경로가 BrandService.create 에 logo_path 로 전달됨
        assert captured.get("name") == "구름"
        assert captured.get("color_hex") == "#5562EA"
        assert captured["create_kwargs"]["logo_path"] is not None
        assert captured["create_kwargs"]["logo_path"].endswith(".png")
        # 응답 status 도 created 여야 (existing fallback 이 아님)
        assert response.status == "created"


class TestCP17GenerateLogoPathInjection:
    """mobile_generate 가 ImageGenerationRequest.logo_path = brand.logo_path 로 주입해야."""

    async def test_image_request_carries_brand_logo_path(self, monkeypatch):
        brand_logo_path = "/tmp/brand-logo-fixture.png"
        brand = SimpleNamespace(
            id=uuid4(),
            name="구름 베이커리",
            color_hex="#ff7448",
            style_prompt="따뜻한 브랜드 가이드",
            logo_path=brand_logo_path,
        )

        captured: dict = {}

        async def fake_load_brand():
            return brand

        async def fake_run_in_threadpool(func, *args, **kwargs):
            return func(*args, **kwargs)

        async def fake_save_generation_outputs(**kwargs):
            return uuid4(), uuid4()

        def fake_generate_ad_image(self, request):
            captured["image_request"] = request
            return ImageGenerationResponse(
                image_data=b"fake-image",
                revised_prompt="warm bakery prompt",
            )

        monkeypatch.setattr(mobile_app, "_load_brand", fake_load_brand)
        monkeypatch.setattr(mobile_app, "run_in_threadpool", fake_run_in_threadpool)
        monkeypatch.setattr(
            mobile_app, "_save_generation_outputs", fake_save_generation_outputs
        )
        monkeypatch.setattr(
            mobile_app.ImageService, "generate_ad_image", fake_generate_ad_image
        )
        monkeypatch.setattr(
            mobile_app, "_langfuse_trace_span", lambda _name: nullcontext()
        )
        monkeypatch.setattr(mobile_app, "_capture_langfuse_trace_id", lambda: "trace")

        await mobile_app.mobile_generate(
            mobile_app.MobileGenerateRequest(
                product_name="아메리카노",
                description="깊은 풍미",
                generation_type="image",
            )
        )

        assert captured["image_request"].logo_path == brand_logo_path


class TestCP17GenerateReferenceAnalysisInjection:
    """reference_image / reference_url 제공 시 ReferenceAnalyzer 결과가 image request 에 주입."""

    async def test_image_request_carries_composition_prompt(self, monkeypatch):
        brand = SimpleNamespace(
            id=uuid4(),
            name="구름 베이커리",
            color_hex="#ff7448",
            style_prompt="따뜻한 브랜드 가이드",
            logo_path=None,
        )

        captured: dict = {}

        async def fake_load_brand():
            return brand

        async def fake_run_in_threadpool(func, *args, **kwargs):
            return func(*args, **kwargs)

        async def fake_save_generation_outputs(**kwargs):
            return uuid4(), uuid4()

        # ReferenceAnalyzer.analyze 를 spy — 호출되면 가짜 구도 텍스트 반환
        def fake_analyze(self, image_path):
            captured["analyzed_path"] = image_path
            return "테스트 구도: 좌상단 강한 광원, 얕은 피사계심도"

        monkeypatch.setattr(
            mobile_app.ReferenceAnalyzer, "analyze", fake_analyze
        )

        def fake_generate_ad_image(self, request):
            captured["image_request"] = request
            return ImageGenerationResponse(
                image_data=b"fake-image",
                revised_prompt="warm bakery prompt",
            )

        monkeypatch.setattr(mobile_app, "_load_brand", fake_load_brand)
        monkeypatch.setattr(mobile_app, "run_in_threadpool", fake_run_in_threadpool)
        monkeypatch.setattr(
            mobile_app, "_save_generation_outputs", fake_save_generation_outputs
        )
        monkeypatch.setattr(
            mobile_app.ImageService, "generate_ad_image", fake_generate_ad_image
        )
        monkeypatch.setattr(
            mobile_app, "_langfuse_trace_span", lambda _name: nullcontext()
        )
        monkeypatch.setattr(mobile_app, "_capture_langfuse_trace_id", lambda: "trace")

        # 1x1 PNG data URL 을 reference_image 로 제공
        tiny_png_b64 = (
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9Z"
            "wTu+EAAAAASUVORK5CYII="
        )
        await mobile_app.mobile_generate(
            mobile_app.MobileGenerateRequest(
                product_name="아메리카노",
                description="깊은 풍미",
                generation_type="image",
                reference_image=mobile_app.DataUrlFile(
                    name="ref.png",
                    data_url=f"data:image/png;base64,{tiny_png_b64}",
                ),
            )
        )

        assert captured["image_request"].reference_analysis != ""
        assert "구도" in captured["image_request"].reference_analysis


class TestCP17TextRequestKeepsReferenceAnalysisEmpty:
    """정책: TextGenerationRequest.reference_analysis 는 항상 빈 문자열.

    [app.py:745-746] '분석 결과는 이미지 프롬프트에만 주입, 텍스트 생성에는 영향 없음
    (brand 톤과 섞이면 안 됨)' 정책을 mobile 에서도 유지.
    """

    async def test_text_request_reference_analysis_empty_even_with_reference(
        self, monkeypatch
    ):
        brand = SimpleNamespace(
            id=uuid4(),
            name="구름 베이커리",
            color_hex="#ff7448",
            style_prompt="따뜻한 브랜드 가이드",
            logo_path=None,
        )

        captured: dict = {}

        async def fake_load_brand():
            return brand

        async def fake_run_in_threadpool(func, *args, **kwargs):
            return func(*args, **kwargs)

        async def fake_save_generation_outputs(**kwargs):
            return uuid4(), uuid4()

        # Reference 분석은 호출되더라도 텍스트 요청에는 빈 문자열만 들어가야 함
        def fake_analyze(self, image_path):
            return "구도 텍스트가 있어도 텍스트 요청에는 안 들어가야 함"

        monkeypatch.setattr(
            mobile_app.ReferenceAnalyzer, "analyze", fake_analyze
        )

        def fake_generate_ad_copy(self, request):
            captured["text_request"] = request
            return TextGenerationResponse(
                ad_copies=["x"], promo_sentences=["y"], story_copies=["z"]
            )

        def fake_generate_ad_image(self, request):
            return ImageGenerationResponse(
                image_data=b"fake-image", revised_prompt="x"
            )

        monkeypatch.setattr(mobile_app, "_load_brand", fake_load_brand)
        monkeypatch.setattr(mobile_app, "run_in_threadpool", fake_run_in_threadpool)
        monkeypatch.setattr(
            mobile_app, "_save_generation_outputs", fake_save_generation_outputs
        )
        monkeypatch.setattr(
            mobile_app.TextService, "generate_ad_copy", fake_generate_ad_copy
        )
        monkeypatch.setattr(
            mobile_app.ImageService, "generate_ad_image", fake_generate_ad_image
        )
        monkeypatch.setattr(
            mobile_app, "_langfuse_trace_span", lambda _name: nullcontext()
        )
        monkeypatch.setattr(mobile_app, "_capture_langfuse_trace_id", lambda: "trace")

        tiny_png_b64 = (
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9Z"
            "wTu+EAAAAASUVORK5CYII="
        )
        await mobile_app.mobile_generate(
            mobile_app.MobileGenerateRequest(
                product_name="아메리카노",
                description="깊은 풍미",
                generation_type="both",
                reference_image=mobile_app.DataUrlFile(
                    name="ref.png",
                    data_url=f"data:image/png;base64,{tiny_png_b64}",
                ),
            )
        )

        assert captured["text_request"].reference_analysis == ""
