"""Stitch 모바일 UI용 경량 FastAPI 앱.

기존 Streamlit 앱이 사용하던 서비스 계층을 재사용해 모바일 HTML 목업(`stitch/`)
에서도 실제 파이프라인을 호출할 수 있게 한다.
"""

from __future__ import annotations

import base64
import binascii
import logging
import re
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Literal
from urllib.parse import urlencode
from uuid import UUID, uuid4

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from openai import (
    APIConnectionError,
    APITimeoutError,
    AuthenticationError,
    BadRequestError,
    RateLimitError,
)
from pydantic import BaseModel, Field

from config.database import AsyncSessionLocal, init_db
from config.settings import get_settings, setup_logging
from models.brand_image import BrandImage
from schemas.image_schema import ImageGenerationRequest
from schemas.instagram_schema import (
    CaptionGenerationRequest,
    CaptionGenerationResponse,
)
from schemas.text_schema import TextGenerationRequest
from services.brand_image_service import BrandImageService
from services.caption_service import CaptionService
from services.image_service import ImageService, ImageServiceError
from services.instagram_auth_adapter import apply_user_token_async
from services.instagram_auth_service import InstagramAuthService
from services.instagram_service import InstagramService
from services.onboarding_service import (
    BrandImageDraft,
    GPTVisionAnalyzer,
    _merge_structured_inputs_into_freetext,
)
from services.product_service import ProductService
from services.text_service import TextService, TextServiceError
from services.upload_service import UploadService
from utils.staging_storage import save_to_brand_assets, save_to_staging

ROOT_DIR = Path(__file__).resolve().parent
DATA_DIR = ROOT_DIR / "data"
STITCH_DIR = ROOT_DIR / "stitch"
ONBOARDING_DIR = DATA_DIR / "onboarding" / "mobile"

settings = get_settings()
logger = logging.getLogger(__name__)
PENDING_INSTAGRAM_STATES: dict[str, tuple[UUID, Literal["settings", "onboarding"], datetime]] = {}


@asynccontextmanager
async def lifespan(_: FastAPI):
    setup_logging(settings)
    await init_db()
    yield


app = FastAPI(title="Gen for SmallBusiness Mobile", lifespan=lifespan)


class DataUrlFile(BaseModel):
    """프런트에서 넘겨주는 base64 파일."""

    name: str = Field(default="upload.png")
    data_url: str


class MobileBrandSummary(BaseModel):
    exists: bool
    brand_name: str | None = None
    brand_color: str | None = None
    brand_atmosphere: str | None = None
    brand_logo_url: str | None = None
    content: str = ""


class MobileInstagramSummary(BaseModel):
    oauth_available: bool
    connect_available: bool = True
    connected: bool
    expired: bool = False
    upload_ready: bool
    connection_source: Literal["oauth", "env", "none"] = "none"
    username: str | None = None
    page_name: str | None = None
    expires_at: datetime | None = None


class MobileBootstrapResponse(BaseModel):
    onboarding_completed: bool
    brand: MobileBrandSummary | None = None
    image_backend_kind: str
    api_ready: bool
    instagram_ready: bool
    instagram: "MobileInstagramSummary"
    product_count: int = 0
    published_reference_count: int = 0


class MobileOnboardingRequest(BaseModel):
    brand_name: str = ""
    brand_color: str | None = None
    brand_atmosphere: str = ""
    freetext: str = ""
    instagram_url: str = ""
    logo: DataUrlFile | None = None
    reference_images: list[DataUrlFile] = Field(default_factory=list)


class MobileOnboardingResponse(BaseModel):
    status: Literal["created", "updated", "existing"]
    brand: MobileBrandSummary
    warnings: list[str] = Field(default_factory=list)


class MobileGenerateRequest(BaseModel):
    product_name: str
    description: str = ""
    goal: str = "일반 홍보"
    generation_type: Literal["text", "image", "both"] = "both"
    tone: str = "기본"
    style: str = "기본"
    reference_url: str = ""
    reference_image: DataUrlFile | None = None


class MobileGenerateResponse(BaseModel):
    generation_type: str
    text_result: dict | None = None
    image_data_url: str | None = None
    revised_prompt: str | None = None


class MobileCaptionRequest(BaseModel):
    product_name: str
    description: str = ""
    style: str = "기본"
    ad_copies: list[str] = Field(default_factory=list)
    is_new_product: bool = False


class MobileStoryRequest(BaseModel):
    image_data_url: str
    text: str


class MobileStoryResponse(BaseModel):
    image_data_url: str


class MobileInstagramConnectResponse(BaseModel):
    mode: Literal["oauth", "placeholder"]
    url: str | None = None
    message: str | None = None


class MobileInstagramConnectRequest(BaseModel):
    source: Literal["settings", "onboarding"] = "settings"


class MobileSimpleStatusResponse(BaseModel):
    status: Literal["ok"]


class MobileFeedUploadRequest(BaseModel):
    product_name: str
    description: str = ""
    goal: str = "일반 홍보"
    caption: str = ""
    image_data_url: str


class MobileStoryUploadRequest(BaseModel):
    image_data_url: str
    caption: str = ""


class MobileUploadResponse(BaseModel):
    status: Literal["ok"]
    kind: Literal["feed", "story"]
    instagram_post_id: str | None = None
    posted_at: datetime | None = None
    account_username: str | None = None
    generated_upload_id: UUID | None = None


_DATA_URL_RE = re.compile(r"^data:(?P<mime>[\w/+.-]+);base64,(?P<data>.+)$")


def _decode_data_url(data_url: str) -> tuple[bytes, str]:
    match = _DATA_URL_RE.match(data_url)
    if not match:
        raise HTTPException(status_code=400, detail="잘못된 data URL 형식입니다.")
    try:
        raw = base64.b64decode(match.group("data"))
    except (ValueError, binascii.Error) as exc:
        raise HTTPException(status_code=400, detail="base64 파일 디코딩에 실패했습니다.") from exc
    return raw, match.group("mime")


def _infer_extension(upload: DataUrlFile) -> str:
    suffix = Path(upload.name).suffix.lower()
    if suffix:
        return suffix

    _, mime = _decode_data_url(upload.data_url)
    if mime == "image/jpeg":
        return ".jpg"
    if mime == "image/webp":
        return ".webp"
    return ".png"


def _to_data_url(image_bytes: bytes, mime: str = "image/png") -> str:
    encoded = base64.b64encode(image_bytes).decode("utf-8")
    return f"data:{mime};base64,{encoded}"


def _mime_to_extension(mime: str) -> str:
    if mime == "image/jpeg":
        return ".jpg"
    if mime == "image/webp":
        return ".webp"
    return ".png"


async def _download_reference_image(reference_url: str) -> bytes:
    cleaned = reference_url.strip()
    if not cleaned:
        raise HTTPException(status_code=400, detail="참고 링크가 비어 있습니다.")
    if not cleaned.startswith(("http://", "https://")):
        raise HTTPException(
            status_code=400,
            detail="참고 링크는 http:// 또는 https:// 로 시작해야 합니다.",
        )

    try:
        async with httpx.AsyncClient(
            timeout=15.0,
            follow_redirects=True,
        ) as client:
            response = await client.get(cleaned)
            response.raise_for_status()
    except httpx.InvalidURL as exc:
        raise HTTPException(status_code=400, detail="참고 링크 형식이 올바르지 않습니다.") from exc
    except httpx.TimeoutException as exc:
        raise HTTPException(
            status_code=504,
            detail="참고 링크에서 이미지를 가져오는 시간이 초과되었습니다.",
        ) from exc
    except httpx.HTTPStatusError as exc:
        raise HTTPException(
            status_code=502,
            detail=f"참고 링크에서 이미지를 가져오지 못했습니다. (HTTP {exc.response.status_code})",
        ) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=502,
            detail="참고 링크에서 이미지를 가져오는 중 네트워크 오류가 발생했습니다.",
        ) from exc

    content_type = response.headers.get("content-type", "").split(";", 1)[0].strip()
    if content_type and not content_type.startswith("image/"):
        raise HTTPException(
            status_code=400,
            detail="참고 링크가 이미지 파일을 가리키지 않습니다.",
        )

    if not response.content:
        raise HTTPException(status_code=400, detail="참고 링크에서 비어 있는 파일을 받았습니다.")

    return response.content


def _relative_data_url(path_str: str | None) -> str | None:
    if not path_str:
        return None

    path = Path(path_str)
    try:
        rel = path.resolve().relative_to(DATA_DIR.resolve())
    except ValueError:
        return None
    return f"/mobile-assets/{rel.as_posix()}"


def _serialize_brand(brand) -> MobileBrandSummary:
    return MobileBrandSummary(
        exists=True,
        brand_name=brand.brand_name,
        brand_color=brand.brand_color,
        brand_atmosphere=brand.brand_atmosphere,
        brand_logo_url=_relative_data_url(brand.brand_logo_path),
        content=brand.content,
    )


def _compose_manual_brand_content(
    *,
    brand_name: str,
    brand_color: str,
    brand_atmosphere: str,
    freetext: str,
    instagram_url: str,
) -> str:
    """Vision 분석 없이도 최소 브랜드 프롬프트를 구성한다."""
    lines: list[str] = []
    if brand_name:
        lines.append(f"이 브랜드의 이름은 {brand_name}입니다.")
    if brand_atmosphere:
        lines.append(f"브랜드가 추구하는 분위기는 {brand_atmosphere}입니다.")
    if brand_color:
        lines.append(f"대표 색상은 {brand_color} 계열을 중심으로 사용합니다.")
    if freetext:
        lines.append(freetext.strip())
    if instagram_url:
        lines.append(f"참고한 인스타그램 레퍼런스는 {instagram_url.strip()} 입니다.")

    if not lines:
        return (
            "이 브랜드는 따뜻하고 기억에 남는 베이커리/카페 경험을 지향합니다. "
            "정돈된 톤으로 편안한 브랜드 인상을 유지해주세요."
        )
    return "\n\n".join(lines)


async def _load_brand_prompt() -> str:
    async with AsyncSessionLocal() as session:
        brand = await BrandImageService(session).get_for_user("default")
    if brand is None:
        raise HTTPException(status_code=409, detail="온보딩이 아직 완료되지 않았습니다.")

    prefix_lines: list[str] = []
    if brand.brand_name:
        prefix_lines.append(f"브랜드 이름: {brand.brand_name}")
    if brand.brand_color:
        prefix_lines.append(f"브랜드 대표 색상: {brand.brand_color}")
    return "\n".join(prefix_lines) + ("\n\n" if prefix_lines else "") + brand.content


def _prune_pending_instagram_states() -> None:
    now = datetime.now(timezone.utc)
    expired = [
        state
        for state, (_, _, expires_at) in PENDING_INSTAGRAM_STATES.items()
        if expires_at <= now
    ]
    for state in expired:
        PENDING_INSTAGRAM_STATES.pop(state, None)


def _issue_instagram_state(
    brand_image_id: UUID,
    source: Literal["settings", "onboarding"],
) -> str:
    _prune_pending_instagram_states()
    state = uuid4().hex
    PENDING_INSTAGRAM_STATES[state] = (
        brand_image_id,
        source,
        datetime.now(timezone.utc) + timedelta(minutes=10),
    )
    return state


def _consume_instagram_state(
    state: str,
) -> tuple[UUID | None, Literal["settings", "onboarding"]]:
    _prune_pending_instagram_states()
    brand_image_id, source, _ = PENDING_INSTAGRAM_STATES.pop(
        state,
        (None, "settings", None),
    )
    return brand_image_id, source


async def _load_brand() -> BrandImage | None:
    async with AsyncSessionLocal() as session:
        return await BrandImageService(session).get_for_user("default")


async def _load_instagram_summary(brand: BrandImage | None) -> MobileInstagramSummary:
    oauth_available = settings.is_instagram_oauth_configured

    if brand is not None:
        connection = await InstagramAuthService(settings).get_connection(brand.id)
        if connection is not None and connection.is_active:
            expires_at = connection.token_expires_at
            if expires_at is not None and expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=timezone.utc)
            expired = bool(
                expires_at and expires_at <= datetime.now(timezone.utc)
            )
            if not expired:
                return MobileInstagramSummary(
                    oauth_available=oauth_available,
                    connect_available=True,
                    connected=True,
                    expired=False,
                    upload_ready=True,
                    connection_source="oauth",
                    username=connection.instagram_username,
                    page_name=connection.facebook_page_name,
                    expires_at=expires_at,
                )
            return MobileInstagramSummary(
                oauth_available=oauth_available,
                connect_available=True,
                connected=False,
                expired=True,
                upload_ready=settings.is_instagram_ready,
                connection_source="env" if settings.is_instagram_ready else "none",
                username=connection.instagram_username,
                page_name=connection.facebook_page_name,
                expires_at=expires_at,
            )

    if settings.is_instagram_ready:
        return MobileInstagramSummary(
            oauth_available=oauth_available,
            connect_available=True,
            connected=False,
            expired=False,
            upload_ready=True,
            connection_source="env",
        )

    return MobileInstagramSummary(
        oauth_available=oauth_available,
        connect_available=True,
        connected=False,
        expired=False,
        upload_ready=False,
        connection_source="none",
    )


async def _load_bootstrap() -> MobileBootstrapResponse:
    async with AsyncSessionLocal() as session:
        brand_service = BrandImageService(session)
        product_service = ProductService(session)
        upload_service = UploadService(session)

        brand = await brand_service.get_for_user("default")
        products = await product_service.list_all()
        uploads = await upload_service.list_published()
    instagram = await _load_instagram_summary(brand)

    return MobileBootstrapResponse(
        onboarding_completed=brand is not None,
        brand=_serialize_brand(brand) if brand is not None else None,
        image_backend_kind=settings.IMAGE_BACKEND_KIND.value,
        api_ready=settings.is_api_ready,
        instagram_ready=instagram.upload_ready,
        instagram=instagram,
        product_count=len(products),
        published_reference_count=len(uploads),
    )


def _split_goal(goal: str) -> tuple[str, str]:
    cleaned = goal.strip()
    if " · " in cleaned:
        goal_category, goal_freeform = cleaned.split(" · ", 1)
        return goal_category.strip(), goal_freeform.strip()
    return cleaned or "일반 홍보", ""


def _consume_upload_generator(
    service: InstagramService,
    image_bytes: bytes,
    caption: str,
    *,
    is_story: bool,
) -> tuple[str | None, datetime | None]:
    generator = (
        service.upload_story(image_bytes, caption)
        if is_story
        else service.upload_real(image_bytes, caption)
    )
    for _ in generator:
        pass
    return service.last_post_id, service.last_posted_at


async def _resolve_upload_context() -> tuple[BrandImage, object]:
    brand = await _load_brand()
    if brand is None:
        raise HTTPException(
            status_code=409,
            detail="브랜드 온보딩을 먼저 완료해야 인스타그램 업로드를 사용할 수 있습니다.",
        )

    upload_settings = settings.model_copy(deep=True)
    upload_ready = await apply_user_token_async(upload_settings, brand)
    if not upload_ready:
        raise HTTPException(
            status_code=409,
            detail="인스타그램 계정을 먼저 연결하거나 관리자 업로드 설정을 준비해야 합니다.",
        )
    return brand, upload_settings


async def _find_or_create_product_for_upload(
    *,
    product_name: str,
    description: str,
    raw_image_path: str,
) -> object:
    async with AsyncSessionLocal() as session:
        product_service = ProductService(session)
        existing = await product_service.find_by_name(product_name)
        normalized_description = description.strip()
        for product in reversed(existing):
            if product.description.strip() == normalized_description:
                return product
        return await product_service.create(
            name=product_name,
            description=description,
            raw_image_path=raw_image_path,
        )


@app.get("/health")
async def health() -> dict:
    return {"ok": True, "image_backend_kind": settings.IMAGE_BACKEND_KIND.value}


@app.get("/api/mobile/bootstrap", response_model=MobileBootstrapResponse)
async def mobile_bootstrap() -> MobileBootstrapResponse:
    return await _load_bootstrap()


@app.get("/api/mobile/instagram/status", response_model=MobileInstagramSummary)
async def mobile_instagram_status() -> MobileInstagramSummary:
    brand = await _load_brand()
    return await _load_instagram_summary(brand)


@app.post(
    "/api/mobile/instagram/connect-url",
    response_model=MobileInstagramConnectResponse,
)
async def mobile_instagram_connect_url(
    payload: MobileInstagramConnectRequest | None = None,
) -> MobileInstagramConnectResponse:
    brand = await _load_brand()
    if brand is None:
        raise HTTPException(
            status_code=409,
            detail="브랜드 온보딩을 먼저 완료해야 인스타그램 계정을 연결할 수 있습니다.",
        )

    source = payload.source if payload is not None else "settings"

    if not settings.is_instagram_oauth_configured:
        return MobileInstagramConnectResponse(
            mode="placeholder",
            message=(
                "현재 환경에는 Meta 로그인 설정이 아직 연결되지 않았습니다. "
                "설정이 준비되면 이 버튼으로 Facebook 로그인과 Instagram 계정 연결을 바로 시작할 수 있습니다."
            ),
        )

    state = _issue_instagram_state(brand.id, source)
    url = InstagramAuthService(settings).generate_oauth_url(state)
    return MobileInstagramConnectResponse(mode="oauth", url=url)


@app.post(
    "/api/mobile/instagram/disconnect",
    response_model=MobileSimpleStatusResponse,
)
async def mobile_instagram_disconnect() -> MobileSimpleStatusResponse:
    brand = await _load_brand()
    if brand is None:
        raise HTTPException(
            status_code=409,
            detail="브랜드 온보딩을 먼저 완료해야 연결을 관리할 수 있습니다.",
        )

    await InstagramAuthService(settings).revoke_connection(brand.id)
    return MobileSimpleStatusResponse(status="ok")


@app.get("/api/mobile/instagram/callback")
async def mobile_instagram_callback(
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
) -> RedirectResponse:
    base_url = "/stitch/settings.html"
    brand_image_id: UUID | None = None
    if state:
        brand_image_id, source = _consume_instagram_state(state)
        base_url = (
            "/stitch/onboarding-instagram.html"
            if source == "onboarding"
            else "/stitch/settings.html"
        )

    if error:
        return RedirectResponse(
            url=f"{base_url}?{urlencode({'ig': 'cancelled'})}",
            status_code=307,
        )
    if not code or not state:
        return RedirectResponse(
            url=f"{base_url}?{urlencode({'ig': 'error', 'ig_message': '인증 응답이 올바르지 않습니다.'})}",
            status_code=307,
        )

    if brand_image_id is None:
        return RedirectResponse(
            url=f"{base_url}?{urlencode({'ig': 'error', 'ig_message': '연결 세션이 만료되어 다시 시도해야 합니다.'})}",
            status_code=307,
        )

    auth_service = InstagramAuthService(settings)
    try:
        short_token = await auth_service.exchange_code_for_token(code)
        long_token, expires_in = await auth_service.exchange_for_long_lived_token(
            short_token
        )
        instagram_info = await auth_service.fetch_instagram_account(long_token)
        await auth_service.save_connection(
            brand_image_id=brand_image_id,
            access_token=long_token,
            expires_in=expires_in,
            instagram_info=instagram_info,
        )
        return RedirectResponse(
            url=f"{base_url}?{urlencode({'ig': 'connected'})}",
            status_code=307,
        )
    except Exception as exc:  # pragma: no cover - external OAuth integration
        logger.exception("인스타그램 OAuth 콜백 처리 실패")
        return RedirectResponse(
            url=f"{base_url}?{urlencode({'ig': 'error', 'ig_message': str(exc)[:180]})}",
            status_code=307,
        )


@app.post("/api/mobile/onboarding/complete", response_model=MobileOnboardingResponse)
async def complete_onboarding(
    payload: MobileOnboardingRequest,
) -> MobileOnboardingResponse:
    warnings: list[str] = []

    async with AsyncSessionLocal() as session:
        brand_service = BrandImageService(session)
        existing = await brand_service.get_for_user("default")

    brand_name = payload.brand_name.strip()
    brand_color = (payload.brand_color or "").strip()
    brand_atmosphere = payload.brand_atmosphere.strip()
    freetext = payload.freetext.strip()
    instagram_url = payload.instagram_url.strip()

    logo_path: str | None = None
    if payload.logo is not None:
        logo_bytes, _ = _decode_data_url(payload.logo.data_url)
        saved_logo = save_to_brand_assets(
            logo_bytes,
            extension=_infer_extension(payload.logo),
        )
        logo_path = str(saved_logo)

    ONBOARDING_DIR.mkdir(parents=True, exist_ok=True)
    analysis_images: list[Path] = []

    for idx, image in enumerate(payload.reference_images[:4], start=1):
        image_bytes, _ = _decode_data_url(image.data_url)
        saved = save_to_staging(
            image_bytes,
            extension=_infer_extension(image),
        )
        logger.info("모바일 온보딩 참고 이미지 저장 (%d): %s", idx, saved)
        analysis_images.append(saved)

    if instagram_url:
        try:
            from backends.insta_capture import InstaCaptureBackend

            capture_backend = InstaCaptureBackend()
            captured = await run_in_threadpool(
                capture_backend.capture_profile,
                instagram_url,
                ONBOARDING_DIR,
                2,
            )
            analysis_images.extend(captured)
        except Exception as exc:  # pragma: no cover - 외부 캡처 의존
            logger.warning("모바일 온보딩 캡처 실패: %s", exc)
            warnings.append(
                "인스타그램 캡처는 실패했지만, 입력한 내용과 업로드한 이미지로 계속 진행했습니다."
            )

    if analysis_images and settings.is_api_ready:
        analyzer = GPTVisionAnalyzer(settings)
        merged_freetext = _merge_structured_inputs_into_freetext(
            freetext=freetext,
            brand_name=brand_name or None,
            brand_color=brand_color or None,
            brand_atmosphere=brand_atmosphere or None,
        )
        try:
            content = await run_in_threadpool(
                analyzer.analyze,
                merged_freetext,
                analysis_images,
            )
        except Exception as exc:  # pragma: no cover - 외부 API 의존
            logger.warning("모바일 온보딩 Vision 분석 실패: %s", exc)
            warnings.append(
                "AI 분석이 실패해서, 입력한 설명을 바탕으로 기본 브랜드 가이드를 만들었습니다."
            )
            content = _compose_manual_brand_content(
                brand_name=brand_name,
                brand_color=brand_color,
                brand_atmosphere=brand_atmosphere,
                freetext=freetext,
                instagram_url=instagram_url,
            )
    else:
        if analysis_images and not settings.is_api_ready:
            warnings.append(
                "OpenAI 설정이 없어 이미지 분석은 건너뛰고, 입력한 내용으로 브랜드 가이드를 저장했습니다."
            )
        content = _compose_manual_brand_content(
            brand_name=brand_name,
            brand_color=brand_color,
            brand_atmosphere=brand_atmosphere,
            freetext=freetext,
            instagram_url=instagram_url,
        )

    draft = BrandImageDraft(
        content=content,
        source_freetext=freetext,
        source_reference_url=instagram_url,
        source_screenshots=[str(path) for path in analysis_images],
        brand_name=brand_name or None,
        brand_color=brand_color or None,
        brand_atmosphere=brand_atmosphere or None,
        brand_logo_path=logo_path,
    )

    async with AsyncSessionLocal() as session:
        brand_service = BrandImageService(session)
        if existing is not None:
            brand_record = await brand_service.update_for_user(
                user_id="default",
                content=draft.content,
                source_freetext=draft.source_freetext,
                source_reference_url=draft.source_reference_url,
                source_screenshots=draft.source_screenshots,
                brand_name=draft.brand_name,
                brand_color=draft.brand_color,
                brand_atmosphere=draft.brand_atmosphere,
                brand_logo_path=draft.brand_logo_path,
            )
            status = "updated"
        else:
            brand_record = await brand_service.create(
                user_id="default",
                content=draft.content,
                source_freetext=draft.source_freetext,
                source_reference_url=draft.source_reference_url,
                source_screenshots=draft.source_screenshots,
                brand_name=draft.brand_name,
                brand_color=draft.brand_color,
                brand_atmosphere=draft.brand_atmosphere,
                brand_logo_path=draft.brand_logo_path,
            )
            status = "created"

    return MobileOnboardingResponse(
        status=status,
        brand=_serialize_brand(brand_record),
        warnings=warnings,
    )


@app.post("/api/mobile/generate", response_model=MobileGenerateResponse)
async def mobile_generate(payload: MobileGenerateRequest) -> MobileGenerateResponse:
    if not payload.product_name.strip():
        raise HTTPException(status_code=400, detail="상품명을 입력해주세요.")

    brand_prompt = await _load_brand_prompt()

    reference_bytes: bytes | None = None
    if payload.reference_image is not None:
        reference_bytes, _ = _decode_data_url(payload.reference_image.data_url)
    elif payload.reference_url.strip():
        reference_bytes = await _download_reference_image(payload.reference_url)

    text_service = TextService(settings)
    image_service = ImageService(settings)

    text_result = None
    image_result = None

    try:
        if payload.generation_type in {"text", "both"}:
            text_result = await run_in_threadpool(
                text_service.generate_ad_copy,
                TextGenerationRequest(
                    product_name=payload.product_name.strip(),
                    description=payload.description.strip(),
                    style=payload.tone,
                    goal=payload.goal.strip(),
                    image_data=reference_bytes,
                    brand_prompt=brand_prompt,
                    is_new_product=False,
                    reference_analysis="",
                ),
            )

        if payload.generation_type in {"image", "both"}:
            hint_copy = ""
            if text_result is not None and text_result.ad_copies:
                hint_copy = text_result.ad_copies[0]

            image_result = await run_in_threadpool(
                image_service.generate_ad_image,
                ImageGenerationRequest(
                    prompt=hint_copy,
                    product_name=payload.product_name.strip(),
                    description=payload.description.strip(),
                    goal=payload.goal.strip(),
                    style=payload.style,
                    image_data=reference_bytes,
                    brand_prompt=brand_prompt,
                    is_new_product=False,
                    reference_analysis="",
                ),
            )
    except TextServiceError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ImageServiceError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return MobileGenerateResponse(
        generation_type=payload.generation_type,
        text_result=text_result.model_dump() if text_result is not None else None,
        image_data_url=(
            _to_data_url(image_result.image_data)
            if image_result is not None
            else None
        ),
        revised_prompt=image_result.revised_prompt if image_result is not None else None,
    )


@app.post("/api/mobile/caption", response_model=CaptionGenerationResponse)
async def mobile_caption(
    payload: MobileCaptionRequest,
) -> CaptionGenerationResponse:
    if not payload.ad_copies:
        raise HTTPException(status_code=400, detail="캡션 생성을 위한 문구가 없습니다.")

    brand_prompt = await _load_brand_prompt()
    caption_service = CaptionService(settings)
    try:
        return await run_in_threadpool(
            caption_service.generate_caption,
            CaptionGenerationRequest(
                product_name=payload.product_name.strip(),
                description=payload.description.strip(),
                ad_copies=payload.ad_copies,
                style=payload.style,
                brand_prompt=brand_prompt,
                is_new_product=payload.is_new_product,
                reference_analysis="",
            ),
        )
    except AuthenticationError as exc:
        raise HTTPException(
            status_code=500,
            detail="OpenAI API 키가 유효하지 않습니다. .env 설정을 확인해주세요.",
        ) from exc
    except RateLimitError as exc:
        raise HTTPException(
            status_code=429,
            detail="캡션 생성 요청 한도를 초과했습니다. 잠시 후 다시 시도해주세요.",
        ) from exc
    except APITimeoutError as exc:
        raise HTTPException(
            status_code=504,
            detail=f"캡션 생성 응답 시간이 초과되었습니다 ({settings.TEXT_TIMEOUT:.0f}초). 잠시 후 다시 시도해주세요.",
        ) from exc
    except BadRequestError as exc:
        raise HTTPException(
            status_code=400,
            detail=f"캡션 생성 요청이 거부되었습니다: {exc.message}",
        ) from exc
    except APIConnectionError as exc:
        raise HTTPException(
            status_code=503,
            detail="OpenAI 서버에 연결할 수 없습니다. 네트워크 상태를 확인해주세요.",
        ) from exc
    except Exception as exc:
        logger.exception("모바일 캡션 생성 실패")
        raise HTTPException(
            status_code=500,
            detail="캡션 생성 중 예기치 않은 오류가 발생했습니다.",
        ) from exc


@app.post("/api/mobile/story", response_model=MobileStoryResponse)
async def mobile_story(payload: MobileStoryRequest) -> MobileStoryResponse:
    if not payload.text.strip():
        raise HTTPException(status_code=400, detail="스토리 문구를 선택해주세요.")

    image_bytes, _ = _decode_data_url(payload.image_data_url)
    image_service = ImageService(settings)
    composed = await run_in_threadpool(
        image_service.compose_story_image,
        image_bytes,
        payload.text.strip(),
    )
    return MobileStoryResponse(image_data_url=_to_data_url(composed))


@app.post("/api/mobile/upload/feed", response_model=MobileUploadResponse)
async def mobile_upload_feed(
    payload: MobileFeedUploadRequest,
) -> MobileUploadResponse:
    if not payload.product_name.strip():
        raise HTTPException(status_code=400, detail="상품명을 먼저 입력해주세요.")

    brand, upload_settings = await _resolve_upload_context()
    image_bytes, mime = _decode_data_url(payload.image_data_url)
    caption = payload.caption.strip()
    saved_path = save_to_staging(image_bytes, extension=_mime_to_extension(mime))
    goal_category, goal_freeform = _split_goal(payload.goal)

    product = await _find_or_create_product_for_upload(
        product_name=payload.product_name.strip(),
        description=payload.description.strip(),
        raw_image_path=str(saved_path),
    )

    instagram_service = InstagramService(upload_settings)
    try:
        post_id, posted_at = await run_in_threadpool(
            _consume_upload_generator,
            instagram_service,
            image_bytes,
            caption,
            is_story=False,
        )
    except (RuntimeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    async with AsyncSessionLocal() as session:
        upload_service = UploadService(session)
        upload = await upload_service.create(
            product_id=product.id,
            image_path=str(saved_path),
            caption=caption,
            goal_category=goal_category,
            goal_freeform=goal_freeform,
        )
        if post_id is not None and posted_at is not None:
            await upload_service.mark_posted(
                upload_id=upload.id,
                instagram_post_id=post_id,
                posted_at=posted_at,
            )

    instagram = await _load_instagram_summary(brand)
    return MobileUploadResponse(
        status="ok",
        kind="feed",
        instagram_post_id=post_id,
        posted_at=posted_at,
        account_username=instagram.username,
        generated_upload_id=upload.id,
    )


@app.post("/api/mobile/upload/story", response_model=MobileUploadResponse)
async def mobile_upload_story(
    payload: MobileStoryUploadRequest,
) -> MobileUploadResponse:
    brand, upload_settings = await _resolve_upload_context()
    image_bytes, _ = _decode_data_url(payload.image_data_url)

    instagram_service = InstagramService(upload_settings)
    try:
        post_id, posted_at = await run_in_threadpool(
            _consume_upload_generator,
            instagram_service,
            image_bytes,
            payload.caption.strip(),
            is_story=True,
        )
    except (RuntimeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    instagram = await _load_instagram_summary(brand)
    return MobileUploadResponse(
        status="ok",
        kind="story",
        instagram_post_id=post_id,
        posted_at=posted_at,
        account_username=instagram.username,
    )


@app.get("/")
async def root() -> RedirectResponse:
    brand = await _load_brand()
    if brand is None:
        return RedirectResponse(url="/stitch/welcome.html", status_code=307)
    return RedirectResponse(url="/stitch/index.html", status_code=307)


app.mount("/mobile-assets", StaticFiles(directory=str(DATA_DIR)), name="mobile-assets")
app.mount("/stitch", StaticFiles(directory=str(STITCH_DIR), html=True), name="stitch")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("mobile_app:app", host="127.0.0.1", port=8007, reload=False)
