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
from fastapi import FastAPI, HTTPException, Request
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
from config.runtime_paths import ROOT_DIR, get_app_data_dir
from config.settings import get_settings, setup_logging
from models.brand import Brand
from schemas.image_schema import ImageGenerationRequest
from schemas.instagram_schema import (
    CaptionGenerationRequest,
    CaptionGenerationResponse,
)
from schemas.text_schema import TextGenerationRequest
from services.brand_service import BrandService
from services.caption_service import CaptionService
from services.generation_service import GenerationService, OutputSpec
from services.image_service import ImageService, ImageServiceError
from services.instagram_auth_adapter import apply_user_token
from services.instagram_auth_service import (
    InstagramAuthService,
    InstagramPageConnectionRequiredError,
)
from services.instagram_service import InstagramService
from services.logo_service import LogoAutoGenerator
from services.onboarding_service import (
    GPTVisionAnalyzer,
    _merge_structured_inputs_into_freetext,
)
from services.reference_service import ReferenceAnalyzer
from services.text_service import TextService, TextServiceError
from services.upload_service import UploadService
from utils.staging_storage import save_to_brand_assets, save_to_staging

DATA_DIR = get_app_data_dir()
STITCH_DIR = ROOT_DIR / "stitch"
ONBOARDING_DIR = DATA_DIR / "onboarding" / "mobile"
LOGO_FONT_PATH = ROOT_DIR / "assets" / "fonts" / "LXGWWenKaiKR-Medium.ttf"
BRAND_ASSETS_DIR = DATA_DIR / "brand_assets"

settings = get_settings()
logger = logging.getLogger(__name__)
PENDING_INSTAGRAM_STATES: dict[str, tuple[UUID, Literal["settings", "onboarding"], datetime]] = {}
TRACE_CLIENT_ID_HEADER = "x-brewgram-client-id"
TRACE_SESSION_ID_HEADER = "x-brewgram-session-id"
TRACE_PAGE_HEADER = "x-brewgram-page"
TRACE_INSTALL_STATE_HEADER = "x-brewgram-install-state"


class _PendingToken:
    """OAuth 완료 후 계정 선택 대기 중인 토큰."""
    __slots__ = ("access_token", "expires_in", "source")

    def __init__(self, access_token: str, expires_in: int, source: str) -> None:
        self.access_token = access_token
        self.expires_in = expires_in
        self.source = source


PENDING_IG_TOKENS: dict[UUID, _PendingToken] = {}


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
    product_image: DataUrlFile | None = None
    reference_url: str = ""
    reference_image: DataUrlFile | None = None
    is_new_product: bool = False
    existing_product_name: str | None = None


class MobileGenerateResponse(BaseModel):
    generation_type: str
    text_result: dict | None = None
    image_data_url: str | None = None
    revised_prompt: str | None = None
    generation_id: UUID | None = None
    generation_output_id: UUID | None = None


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


class MobileInstagramCandidate(BaseModel):
    instagram_account_id: str
    instagram_username: str | None = None
    facebook_page_id: str | None = None
    facebook_page_name: str | None = None


class MobileInstagramCandidatesResponse(BaseModel):
    candidates: list[MobileInstagramCandidate]
    env_account_id: str | None = None  # .env INSTAGRAM_ACCOUNT_ID — 수동 입력 기본값


class MobileInstagramSelectRequest(BaseModel):
    instagram_account_id: str


class MobileInstagramManualRequest(BaseModel):
    instagram_username: str


class MobileInstagramConnectedResponse(BaseModel):
    status: Literal["connected"]
    username: str | None = None


class MobileFeedUploadRequest(BaseModel):
    product_name: str
    description: str = ""
    goal: str = "일반 홍보"
    caption: str = ""
    image_data_url: str
    generation_output_id: UUID | None = None


class MobileStoryUploadRequest(BaseModel):
    image_data_url: str
    caption: str = ""
    generation_output_id: UUID | None = None


class MobileUploadResponse(BaseModel):
    status: Literal["ok"]
    kind: Literal["feed", "story"]
    instagram_post_id: str | None = None
    posted_at: datetime | None = None
    account_username: str | None = None
    generated_upload_id: UUID | None = None


class MobileProductGroup(BaseModel):
    product_name: str
    product_description: str | None = None
    product_image_url: str | None = None
    latest_generation_id: UUID | None = None
    generation_count: int = 0


class MobileProductsResponse(BaseModel):
    products: list[MobileProductGroup]


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


async def _capture_instagram_with_worker(instagram_url: str) -> list[Path]:
    """Mac 로컬 캡처 워커가 노출되어 있으면 Instagram 캡처 이미지를 받아 저장한다."""
    worker_url = settings.INSTAGRAM_CAPTURE_WORKER_URL.strip()
    if not worker_url:
        return []

    endpoint = worker_url.rstrip("/")
    if not endpoint.endswith("/capture"):
        endpoint = f"{endpoint}/capture"

    headers: dict[str, str] = {}
    if settings.INSTAGRAM_CAPTURE_WORKER_TOKEN:
        headers["Authorization"] = f"Bearer {settings.INSTAGRAM_CAPTURE_WORKER_TOKEN}"

    async with httpx.AsyncClient(
        timeout=settings.INSTAGRAM_CAPTURE_WORKER_TIMEOUT,
        follow_redirects=True,
    ) as client:
        response = await client.post(
            endpoint,
            json={"url": instagram_url, "count": 2},
            headers=headers,
        )
        response.raise_for_status()

    payload = response.json()
    images = payload.get("images") or []
    saved_paths: list[Path] = []
    for idx, image in enumerate(images[:4], start=1):
        data_url = image.get("data_url") if isinstance(image, dict) else None
        if not data_url:
            continue
        image_bytes, mime = _decode_data_url(data_url)
        saved = save_to_staging(image_bytes, extension=_mime_to_extension(mime))
        logger.info("Mac 캡처 워커 이미지 저장 (%d): %s", idx, saved)
        saved_paths.append(saved)

    if not saved_paths:
        raise ValueError("Mac 캡처 워커가 이미지를 반환하지 않았습니다.")
    return saved_paths


def _relative_data_url(path_str: str | None) -> str | None:
    if not path_str:
        return None

    path = Path(path_str)
    try:
        rel = path.resolve().relative_to(DATA_DIR.resolve())
    except ValueError:
        return None
    return f"/mobile-assets/{rel.as_posix()}"


def _serialize_brand(brand: Brand) -> MobileBrandSummary:
    return MobileBrandSummary(
        exists=True,
        brand_name=brand.name,
        brand_color=brand.color_hex,
        brand_atmosphere=brand.input_mood,
        brand_logo_url=_relative_data_url(brand.logo_path),
        content=brand.style_prompt,
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


def _build_brand_prompt(brand: Brand) -> str:
    prefix_lines: list[str] = []
    if brand.name:
        prefix_lines.append(f"브랜드 이름: {brand.name}")
    if brand.color_hex:
        prefix_lines.append(f"브랜드 대표 색상: {brand.color_hex}")
    return "\n".join(prefix_lines) + ("\n\n" if prefix_lines else "") + brand.style_prompt


async def _load_brand_prompt() -> str:
    brand = await _load_brand()
    if brand is None:
        raise HTTPException(status_code=409, detail="온보딩이 아직 완료되지 않았습니다.")
    return _build_brand_prompt(brand)


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
    brand_id: UUID,
    source: Literal["settings", "onboarding"],
) -> str:
    _prune_pending_instagram_states()
    state = uuid4().hex
    PENDING_INSTAGRAM_STATES[state] = (
        brand_id,
        source,
        datetime.now(timezone.utc) + timedelta(minutes=10),
    )
    return state


def _consume_instagram_state(
    state: str,
) -> tuple[UUID | None, Literal["settings", "onboarding"]]:
    _prune_pending_instagram_states()
    brand_id, source, _ = PENDING_INSTAGRAM_STATES.pop(
        state,
        (None, "settings", None),
    )
    return brand_id, source


async def _load_brand() -> Brand | None:
    async with AsyncSessionLocal() as session:
        return await BrandService(session).get_first()


async def _load_instagram_summary(brand: Brand | None) -> MobileInstagramSummary:
    oauth_available = settings.is_instagram_oauth_configured_for("mobile")

    if brand is not None:
        connection = await InstagramAuthService(settings).get_connection(brand.id)
        username = getattr(brand, "instagram_username", None) or getattr(
            connection,
            "instagram_username",
            None,
        )
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
                    username=username,
                    page_name=connection.facebook_page_name,
                    expires_at=expires_at,
                )
            return MobileInstagramSummary(
                oauth_available=oauth_available,
                connect_available=True,
                connected=False,
                expired=True,
                upload_ready=False,
                connection_source="none",
                username=username,
                page_name=connection.facebook_page_name,
                expires_at=expires_at,
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
        brand_service = BrandService(session)
        generation_service = GenerationService(session)
        upload_service = UploadService(session)

        brand = await brand_service.get_first()
        products = await generation_service.list_products(brand.id) if brand else []
        uploads = await upload_service.list_published(brand_id=brand.id) if brand else []
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


async def apply_user_token_async(upload_settings, brand: Brand) -> bool:
    """동기 어댑터를 async FastAPI 경로에서 사용할 수 있게 감싼다."""
    return await run_in_threadpool(apply_user_token, upload_settings, brand)


async def _resolve_upload_context() -> tuple[Brand, object]:
    brand = await _load_brand()
    if brand is None:
        raise HTTPException(
            status_code=409,
            detail="브랜드 온보딩을 먼저 완료해야 인스타그램 업로드를 사용할 수 있습니다.",
        )

    upload_settings = settings.model_copy(deep=True)
    if not getattr(brand, "instagram_account_id", None):
        raise HTTPException(
            status_code=409,
            detail="인스타그램 계정을 먼저 연결한 뒤 업로드를 진행해주세요.",
        )

    connection = await InstagramAuthService(settings).get_connection(brand.id)
    if connection is None or not connection.is_active:
        raise HTTPException(
            status_code=409,
            detail="인스타그램 계정을 먼저 연결한 뒤 업로드를 진행해주세요.",
        )

    expires_at = connection.token_expires_at
    if expires_at is not None and expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if expires_at is not None and expires_at <= datetime.now(timezone.utc):
        raise HTTPException(
            status_code=409,
            detail="인스타그램 연결이 만료되었습니다. 다시 연결한 뒤 업로드를 진행해주세요.",
        )

    try:
        upload_ready = await apply_user_token_async(upload_settings, brand)
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    if not upload_ready:
        raise HTTPException(
            status_code=409,
            detail="인스타그램 계정을 먼저 연결한 뒤 업로드를 진행해주세요.",
        )
    return brand, upload_settings


def _load_existing_product_bytes(
    brand_id: UUID, product_name: str
) -> tuple[bytes, str] | None:
    """기존 상품의 product_image_path 가 살아있는 최근 Generation 에서 bytes + path 반환.

    list_products() 는 "가장 최근" Generation 을 반환하므로 product_image_path 가 NULL
    일 수 있다. 여기서는 경로가 있는 첫 번째 Generation 을 찾는다.

    파일이 없거나 오류 시 None 반환 (폴백: 텍스트 프롬프트만으로 생성 계속).
    """
    import asyncio

    async def _fetch() -> tuple[bytes, str] | None:
        async with AsyncSessionLocal() as session:
            service = GenerationService(session)
            products = await service.list_products(brand_id)
        # 같은 이름 상품 중 product_image_path 가 있는 첫 번째 선택
        matched = next(
            (
                p
                for p in products
                if p.product_name == product_name and p.product_image_path
            ),
            None,
        )
        if matched is None or matched.product_image_path is None:
            return None
        try:
            return Path(matched.product_image_path).read_bytes(), matched.product_image_path
        except OSError as exc:
            logger.warning("기존 상품 사진 로드 실패 (%s): %s", product_name, exc)
            return None

    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # FastAPI 이벤트 루프 안 — run_coroutine_threadsafe 사용 불가이므로
            # asyncio.ensure_future 대신 nest_asyncio 없이 새 루프에서 실행
            import concurrent.futures

            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(asyncio.run, _fetch())
                return future.result()
        return loop.run_until_complete(_fetch())
    except Exception as exc:  # pragma: no cover
        logger.warning("기존 상품 사진 로드 실패 (%s): %s", product_name, exc)
        return None


async def _save_generation_outputs(
    *,
    brand: Brand,
    product_name: str,
    description: str,
    goal: str,
    tone: str,
    text_result: dict | None,
    image_bytes: bytes | None,
    langfuse_trace_id: str | None = None,
    product_image_bytes: bytes | None = None,
    existing_product_image_path: str | None = None,
    is_new_product: bool = False,
) -> tuple[UUID | None, UUID | None]:
    outputs: list[OutputSpec] = []
    if image_bytes:
        saved_path = save_to_staging(image_bytes, extension=".png")
        outputs.append(OutputSpec(kind="image", content_path=str(saved_path)))
    if text_result:
        for copy in text_result.get("ad_copies", []) or []:
            outputs.append(OutputSpec(kind="ad_copy", content_text=copy))
        for sentence in text_result.get("promo_sentences", []) or []:
            outputs.append(OutputSpec(kind="promo_sentence", content_text=sentence))
        for copy in text_result.get("story_copies", []) or []:
            outputs.append(OutputSpec(kind="story_copy", content_text=copy))

    if not outputs:
        return None, None

    product_image_path: str | None = None
    if product_image_bytes:
        product_image_path = str(save_to_staging(product_image_bytes, extension=".png"))
    elif existing_product_image_path:
        # 기존 상품 재생성: 원본 경로 그대로 승계 (새로 staging 저장하지 않음)
        product_image_path = existing_product_image_path

    async with AsyncSessionLocal() as session:
        generation_service = GenerationService(session)
        generation = await generation_service.create_with_outputs(
            brand_id=brand.id,
            reference_image_id=None,
            product_name=product_name,
            product_description=description,
            product_image_path=product_image_path,
            goal=goal,
            tone=tone,
            is_new_product=is_new_product,
            outputs=outputs,
            langfuse_trace_id=langfuse_trace_id,
        )
    image_output_id = next(
        (output.id for output in generation.outputs if output.kind == "image"),
        None,
    )
    return generation.id, image_output_id


def _require_generation_output_id(
    generation_output_id: UUID | None,
) -> UUID:
    if generation_output_id is None:
        raise HTTPException(
            status_code=409,
            detail="광고 이미지를 다시 생성한 뒤 업로드를 시도해주세요.",
        )
    return generation_output_id


def _langfuse_trace_span(name: str):
    """Langfuse 루트 span 컨텍스트 매니저.

    Streamlit app.py 와 같은 방식으로 모바일 요청 단위를 trace 로 묶는다.
    Langfuse 가 비활성이면 nullcontext 로 폴백한다.
    """
    import contextlib

    try:
        from langfuse import get_client

        client = get_client()
        return client.start_as_current_observation(name=name, as_type="span")
    except Exception as exc:  # noqa: BLE001
        logger.warning("Langfuse span 시작 실패 → 추적 없이 진행: %s", exc)
        return contextlib.nullcontext()


def _sanitize_langfuse_value(value: str | None) -> str | None:
    if value is None:
        return None
    ascii_value = value.encode("ascii", "ignore").decode("ascii").strip()
    if not ascii_value:
        return None
    return ascii_value[:200]


def _request_trace_attributes(
    request: Request | None,
    *,
    tags: list[str] | None = None,
    metadata: dict[str, str] | None = None,
) -> tuple[str | None, str | None, list[str], dict[str, str]]:
    base_tags = ["surface:mobile"]
    base_metadata = {"surface": "mobile"}

    if request is not None:
        page = _sanitize_langfuse_value(request.headers.get(TRACE_PAGE_HEADER))
        install_state = _sanitize_langfuse_value(
            request.headers.get(TRACE_INSTALL_STATE_HEADER)
        )
        request_path = _sanitize_langfuse_value(request.url.path)
        client_id = _sanitize_langfuse_value(
            request.headers.get(TRACE_CLIENT_ID_HEADER)
        )
        session_id = _sanitize_langfuse_value(
            request.headers.get(TRACE_SESSION_ID_HEADER)
        )

        if page:
            base_tags.append(f"page:{page}")
            base_metadata["page"] = page
        if install_state:
            base_tags.append(f"install:{install_state}")
            base_metadata["install_state"] = install_state
        if request_path:
            base_metadata["request_path"] = request_path
    else:
        client_id = None
        session_id = None

    if tags:
        for tag in tags:
            cleaned = _sanitize_langfuse_value(tag)
            if cleaned:
                base_tags.append(cleaned)

    if metadata:
        for key, value in metadata.items():
            cleaned_key = _sanitize_langfuse_value(key)
            cleaned_value = _sanitize_langfuse_value(value)
            if cleaned_key and cleaned_value:
                base_metadata[cleaned_key] = cleaned_value

    deduped_tags = list(dict.fromkeys(base_tags))
    return client_id, session_id, deduped_tags, base_metadata


def _langfuse_trace_attributes(
    request: Request | None = None,
    *,
    tags: list[str] | None = None,
    metadata: dict[str, str] | None = None,
):
    import contextlib

    try:
        from langfuse import propagate_attributes

        user_id, session_id, trace_tags, trace_metadata = _request_trace_attributes(
            request,
            tags=tags,
            metadata=metadata,
        )
        kwargs: dict[str, object] = {}
        if user_id:
            kwargs["user_id"] = user_id
        if session_id:
            kwargs["session_id"] = session_id
        if trace_tags:
            kwargs["tags"] = trace_tags
        if trace_metadata:
            kwargs["metadata"] = trace_metadata

        if not kwargs:
            return contextlib.nullcontext()
        return propagate_attributes(**kwargs)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Langfuse 속성 전파 실패 → 기본 trace 로 진행: %s", exc)
        return contextlib.nullcontext()


def _capture_langfuse_trace_id() -> str | None:
    """현재 활성 span 의 trace_id 반환."""
    try:
        from langfuse import get_client

        return get_client().get_current_trace_id()
    except Exception:  # noqa: BLE001
        return None


def _mobile_generation_trace_name(generation_type: str) -> str:
    if generation_type == "text":
        return "generation.text_only"
    if generation_type == "image":
        return "generation.image_only"
    return "generation.combined"


@app.get("/health")
async def health() -> dict:
    return {"ok": True, "image_backend_kind": settings.IMAGE_BACKEND_KIND.value}


@app.get("/api/mobile/bootstrap", response_model=MobileBootstrapResponse)
async def mobile_bootstrap() -> MobileBootstrapResponse:
    return await _load_bootstrap()


@app.get("/api/mobile/products", response_model=MobileProductsResponse)
async def mobile_list_products() -> MobileProductsResponse:
    brand = await _load_brand()
    if brand is None:
        return MobileProductsResponse(products=[])

    async with AsyncSessionLocal() as session:
        service = GenerationService(session)
        product_groups = await service.list_products(brand.id)

    result: list[MobileProductGroup] = []
    for pg in product_groups:
        image_url: str | None = None
        if pg.product_image_path:
            image_url = _relative_data_url(pg.product_image_path)
        result.append(
            MobileProductGroup(
                product_name=pg.product_name,
                product_description=pg.product_description,
                product_image_url=image_url,
                latest_generation_id=pg.latest_generation_id,
                generation_count=pg.generation_count,
            )
        )
    return MobileProductsResponse(products=result)


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

    if not settings.is_instagram_oauth_configured_for("mobile"):
        return MobileInstagramConnectResponse(
            mode="placeholder",
            message=(
                "현재 환경에는 Meta 로그인 설정이 아직 연결되지 않았습니다. "
                "설정이 준비되면 이 버튼으로 Facebook 로그인과 Instagram 계정 연결을 바로 시작할 수 있습니다."
            ),
        )

    state = _issue_instagram_state(brand.id, source)
    url = InstagramAuthService(settings).generate_oauth_url(state, surface="mobile")
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
    brand_id: UUID | None = None
    if state:
        brand_id, source = _consume_instagram_state(state)
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

    if brand_id is None:
        return RedirectResponse(
            url=f"{base_url}?{urlencode({'ig': 'error', 'ig_message': '연결 세션이 만료되어 다시 시도해야 합니다.'})}",
            status_code=307,
        )

    auth_service = InstagramAuthService(settings)
    try:
        short_token = await auth_service.exchange_code_for_token(
            code,
            surface="mobile",
        )
        long_token, expires_in = await auth_service.exchange_for_long_lived_token(
            short_token
        )
        candidates = await auth_service.list_candidate_accounts(long_token)

        if len(candidates) == 1:
            # 후보 1개 → 바로 저장
            await auth_service.save_connection(
                brand_id=brand_id,
                access_token=long_token,
                expires_in=expires_in,
                ig_info=candidates[0],
            )
            return RedirectResponse(
                url=f"{base_url}?{urlencode({'ig': 'connected'})}",
                status_code=307,
            )
        elif len(candidates) >= 2:
            # 후보 여러 개 → 대기 저장 후 선택 UI 로
            PENDING_IG_TOKENS[brand_id] = _PendingToken(
                access_token=long_token,
                expires_in=expires_in,
                source=source,
            )
            return RedirectResponse(
                url=f"{base_url}?{urlencode({'ig': 'select_required'})}",
                status_code=307,
            )
        else:
            # IG 연결된 페이지 없음 → 수동 입력 UI 로
            PENDING_IG_TOKENS[brand_id] = _PendingToken(
                access_token=long_token,
                expires_in=expires_in,
                source=source,
            )
            return RedirectResponse(
                url=f"{base_url}?{urlencode({'ig': 'manual_required'})}",
                status_code=307,
            )
    except InstagramPageConnectionRequiredError as exc:
        return RedirectResponse(
            url=f"{base_url}?{urlencode({'ig': 'page_required', 'ig_message': str(exc)[:180]})}",
            status_code=307,
        )
    except Exception as exc:  # pragma: no cover - external OAuth integration
        logger.exception("인스타그램 OAuth 콜백 처리 실패")
        return RedirectResponse(
            url=f"{base_url}?{urlencode({'ig': 'error', 'ig_message': str(exc)[:180]})}",
            status_code=307,
        )


@app.get(
    "/api/mobile/instagram/candidates",
    response_model=MobileInstagramCandidatesResponse,
)
async def mobile_instagram_candidates() -> MobileInstagramCandidatesResponse:
    """OAuth 완료 후 선택 대기 중인 IG 후보 목록 반환."""
    brand = await _load_brand()
    if brand is None:
        raise HTTPException(status_code=409, detail="브랜드 온보딩을 먼저 완료해야 합니다.")

    pending = PENDING_IG_TOKENS.get(brand.id)
    if pending is None:
        raise HTTPException(status_code=404, detail="대기 중인 Instagram 연결 정보가 없습니다.")

    auth_service = InstagramAuthService(settings)
    raw_candidates = await auth_service.list_candidate_accounts(pending.access_token)

    env_id = settings.INSTAGRAM_ACCOUNT_ID or None
    return MobileInstagramCandidatesResponse(
        candidates=[MobileInstagramCandidate(**c) for c in raw_candidates],
        env_account_id=env_id,
    )


@app.post(
    "/api/mobile/instagram/select-account",
    response_model=MobileInstagramConnectedResponse,
)
async def mobile_instagram_select_account(
    payload: MobileInstagramSelectRequest,
) -> MobileInstagramConnectedResponse:
    """후보 목록에서 계정을 선택해 저장."""
    brand = await _load_brand()
    if brand is None:
        raise HTTPException(status_code=409, detail="브랜드 온보딩을 먼저 완료해야 합니다.")

    pending = PENDING_IG_TOKENS.get(brand.id)
    if pending is None:
        raise HTTPException(status_code=404, detail="대기 중인 Instagram 연결 정보가 없습니다.")

    auth_service = InstagramAuthService(settings)
    candidates = await auth_service.list_candidate_accounts(pending.access_token)

    selected = next(
        (c for c in candidates if c["instagram_account_id"] == payload.instagram_account_id),
        None,
    )
    if selected is None:
        raise HTTPException(status_code=400, detail="선택한 Instagram 계정을 찾을 수 없습니다.")

    await auth_service.save_connection(
        brand_id=brand.id,
        access_token=pending.access_token,
        expires_in=pending.expires_in,
        ig_info=selected,
    )
    PENDING_IG_TOKENS.pop(brand.id, None)

    return MobileInstagramConnectedResponse(
        status="connected",
        username=selected.get("instagram_username"),
    )


@app.post(
    "/api/mobile/instagram/manual-account",
    response_model=MobileInstagramConnectedResponse,
)
async def mobile_instagram_manual_account(
    payload: MobileInstagramManualRequest,
) -> MobileInstagramConnectedResponse:
    """수동 입력 @username 으로 계정 연결."""
    brand = await _load_brand()
    if brand is None:
        raise HTTPException(status_code=409, detail="브랜드 온보딩을 먼저 완료해야 합니다.")

    pending = PENDING_IG_TOKENS.get(brand.id)
    if pending is None:
        raise HTTPException(status_code=404, detail="대기 중인 Instagram 연결 정보가 없습니다.")

    auth_service = InstagramAuthService(settings)
    ig_info = await auth_service.resolve_instagram_username(
        pending.access_token, payload.instagram_username
    )

    await auth_service.save_connection(
        brand_id=brand.id,
        access_token=pending.access_token,
        expires_in=pending.expires_in,
        ig_info=ig_info,
    )
    PENDING_IG_TOKENS.pop(brand.id, None)

    return MobileInstagramConnectedResponse(
        status="connected",
        username=ig_info.get("instagram_username"),
    )


@app.post("/api/mobile/onboarding/complete", response_model=MobileOnboardingResponse)
async def complete_onboarding(
    payload: MobileOnboardingRequest,
    request: Request = None,
) -> MobileOnboardingResponse:
    async with AsyncSessionLocal() as session:
        existing = await BrandService(session).get_first()
    if existing is not None:
        return MobileOnboardingResponse(
            status="existing",
            brand=_serialize_brand(existing),
            warnings=[],
        )

    warnings: list[str] = []

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
    else:
        # CP14: 로고 미업로드 시 PIL 워드마크 자동 생성 (Streamlit 흐름과 동등).
        # CP15 OpenAIImageBackend 가 logo_path 를 필수로 요구하므로 항상 채워둔다.
        BRAND_ASSETS_DIR.mkdir(parents=True, exist_ok=True)
        generator = LogoAutoGenerator(
            font_path=LOGO_FONT_PATH,
            save_dir=BRAND_ASSETS_DIR,
        )
        saved_logo = await run_in_threadpool(
            generator.generate_and_save,
            name=brand_name,
            color_hex=brand_color or "#ff7448",
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
        captured: list[Path] = []
        if settings.INSTAGRAM_CAPTURE_WORKER_URL.strip():
            try:
                captured = await _capture_instagram_with_worker(instagram_url)
                analysis_images.extend(captured)
            except Exception as exc:  # pragma: no cover - 외부 Mac 워커 의존
                logger.warning("모바일 온보딩 Mac 캡처 워커 실패: %s", exc)
                warnings.append(
                    "Mac 캡처 워커는 실패했지만, 입력한 내용과 업로드한 이미지로 계속 진행했습니다."
                )

        if not captured:
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
            description=freetext,
            name=brand_name,
            color_hex=brand_color,
            mood=brand_atmosphere,
        )
        try:
            with _langfuse_trace_span("onboarding.analysis"):
                with _langfuse_trace_attributes(
                    request,
                    tags=["feature:onboarding"],
                    metadata={
                        "analysis_image_count": str(len(analysis_images)),
                        "has_instagram_url": "true" if bool(instagram_url) else "false",
                    },
                ):
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

    async with AsyncSessionLocal() as session:
        brand_service = BrandService(session)
        brand_record = await brand_service.create(
            name=brand_name,
            color_hex=brand_color or "#ff7448",
            logo_path=logo_path,
            input_instagram_url=instagram_url,
            input_description=freetext,
            input_mood=brand_atmosphere,
            style_prompt=content,
        )

    return MobileOnboardingResponse(
        status="created",
        brand=_serialize_brand(brand_record),
        warnings=warnings,
    )


@app.post("/api/mobile/generate", response_model=MobileGenerateResponse)
async def mobile_generate(
    payload: MobileGenerateRequest,
    request: Request = None,
) -> MobileGenerateResponse:
    if not payload.product_name.strip():
        raise HTTPException(status_code=400, detail="상품명을 입력해주세요.")

    brand = await _load_brand()
    if brand is None:
        raise HTTPException(status_code=409, detail="온보딩이 아직 완료되지 않았습니다.")
    brand_prompt = _build_brand_prompt(brand)

    product_image_bytes: bytes | None = None
    existing_product_image_path: str | None = None
    if payload.product_image is not None:
        product_image_bytes, _ = _decode_data_url(payload.product_image.data_url)
    elif not payload.is_new_product and payload.existing_product_name:
        loaded = _load_existing_product_bytes(
            brand.id, payload.existing_product_name
        )
        if loaded is not None:
            product_image_bytes, existing_product_image_path = loaded

    # 신상품인데 사진이 없으면 400
    if payload.is_new_product and product_image_bytes is None:
        raise HTTPException(status_code=400, detail="신상품 등록 시 상품 사진을 먼저 업로드해주세요.")

    reference_bytes: bytes | None = None
    if payload.reference_image is not None:
        reference_bytes, _ = _decode_data_url(payload.reference_image.data_url)
    elif payload.reference_url.strip():
        reference_bytes = await _download_reference_image(payload.reference_url)

    # 참조 이미지가 있으면 구도 분석 → ImageGenerationRequest.reference_analysis 로 주입.
    # Streamlit 흐름과 동등 (app.py:_prepare_reference). 텍스트 요청에는 주입하지 않음
    # (정책: brand 톤과 섞이면 안 됨).
    composition_prompt = ""
    if reference_bytes is not None:
        try:
            ref_path = save_to_staging(reference_bytes, extension=".png")
            composition_prompt = await run_in_threadpool(
                ReferenceAnalyzer(settings).analyze, ref_path
            )
        except Exception as exc:  # pragma: no cover - 외부 Vision API 의존
            logger.warning("참조 이미지 구도 분석 실패: %s", exc)
            composition_prompt = ""

    text_service = TextService(settings)
    image_service = ImageService(settings)

    text_result = None
    image_result = None
    text_payload: dict | None = None
    generation_id: UUID | None = None
    generation_output_id: UUID | None = None
    langfuse_trace_id: str | None = None

    try:
        with _langfuse_trace_span(
            _mobile_generation_trace_name(payload.generation_type)
        ):
            with _langfuse_trace_attributes(
                request,
                tags=[
                    "feature:generation",
                    f"generation_type:{payload.generation_type}",
                ],
                metadata={
                    "product_name_length": str(len(payload.product_name.strip())),
                    "description_length": str(len(payload.description.strip())),
                    "is_new_product": "true" if payload.is_new_product else "false",
                    "has_reference_image": (
                        "true"
                        if payload.reference_image is not None or bool(payload.reference_url.strip())
                        else "false"
                    ),
                    "has_product_image": "true" if product_image_bytes is not None else "false",
                    "has_existing_product_name": (
                        "true" if bool(payload.existing_product_name) else "false"
                    ),
                },
            ):
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
                    text_payload = text_result.model_dump()

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
                            image_data=product_image_bytes,
                            brand_prompt=brand_prompt,
                            is_new_product=payload.is_new_product,
                            reference_analysis=composition_prompt,
                            logo_path=brand.logo_path,
                        ),
                    )
                langfuse_trace_id = _capture_langfuse_trace_id()

        generation_id, generation_output_id = await _save_generation_outputs(
            brand=brand,
            product_name=payload.product_name.strip(),
            description=payload.description.strip(),
            goal=payload.goal.strip() or "일반 홍보",
            tone=payload.tone,
            text_result=text_payload,
            image_bytes=image_result.image_data if image_result is not None else None,
            langfuse_trace_id=langfuse_trace_id,
            product_image_bytes=product_image_bytes if payload.is_new_product else None,
            existing_product_image_path=existing_product_image_path,
            is_new_product=payload.is_new_product,
        )
    except TextServiceError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ImageServiceError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return MobileGenerateResponse(
        generation_type=payload.generation_type,
        text_result=text_payload,
        image_data_url=(
            _to_data_url(image_result.image_data)
            if image_result is not None
            else None
        ),
        revised_prompt=image_result.revised_prompt if image_result is not None else None,
        generation_id=generation_id,
        generation_output_id=generation_output_id,
    )


@app.post("/api/mobile/caption", response_model=CaptionGenerationResponse)
async def mobile_caption(
    payload: MobileCaptionRequest,
    request: Request = None,
) -> CaptionGenerationResponse:
    if not payload.ad_copies:
        raise HTTPException(status_code=400, detail="캡션 생성을 위한 문구가 없습니다.")

    brand_prompt = await _load_brand_prompt()
    caption_service = CaptionService(settings)
    try:
        with _langfuse_trace_span("generation.caption"):
            with _langfuse_trace_attributes(
                request,
                tags=["feature:caption"],
                metadata={
                    "is_new_product": "true" if payload.is_new_product else "false",
                    "ad_copy_count": str(len(payload.ad_copies)),
                    "product_name_length": str(len(payload.product_name.strip())),
                },
            ):
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
async def mobile_story(
    payload: MobileStoryRequest,
    request: Request = None,
) -> MobileStoryResponse:
    if not payload.text.strip():
        raise HTTPException(status_code=400, detail="스토리 문구를 선택해주세요.")

    image_bytes, _ = _decode_data_url(payload.image_data_url)
    image_service = ImageService(settings)
    with _langfuse_trace_span("generation.story"):
        with _langfuse_trace_attributes(
            request,
            tags=["feature:story"],
            metadata={"text_length": str(len(payload.text.strip()))},
        ):
            composed = await run_in_threadpool(
                image_service.compose_story_image,
                image_bytes,
                payload.text.strip(),
            )
    return MobileStoryResponse(image_data_url=_to_data_url(composed))


@app.post("/api/mobile/upload/feed", response_model=MobileUploadResponse)
async def mobile_upload_feed(
    payload: MobileFeedUploadRequest,
    request: Request = None,
) -> MobileUploadResponse:
    if not payload.product_name.strip():
        raise HTTPException(status_code=400, detail="상품명을 먼저 입력해주세요.")

    brand, upload_settings = await _resolve_upload_context()
    image_bytes, _ = _decode_data_url(payload.image_data_url)
    caption = payload.caption.strip()
    generation_output_id = _require_generation_output_id(payload.generation_output_id)

    instagram_service = InstagramService(upload_settings)
    try:
        with _langfuse_trace_span("instagram.upload.feed"):
            with _langfuse_trace_attributes(
                request,
                tags=["feature:upload", "upload:feed"],
                metadata={"has_caption": "true" if bool(caption) else "false"},
            ):
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
            generation_output_id=generation_output_id,
            kind="feed",
            caption=caption,
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
    request: Request = None,
) -> MobileUploadResponse:
    brand, upload_settings = await _resolve_upload_context()
    image_bytes, _ = _decode_data_url(payload.image_data_url)
    generation_output_id = _require_generation_output_id(payload.generation_output_id)

    instagram_service = InstagramService(upload_settings)
    try:
        with _langfuse_trace_span("instagram.upload.story"):
            with _langfuse_trace_attributes(
                request,
                tags=["feature:upload", "upload:story"],
                metadata={
                    "has_caption": "true" if bool(payload.caption.strip()) else "false"
                },
            ):
                post_id, posted_at = await run_in_threadpool(
                    _consume_upload_generator,
                    instagram_service,
                    image_bytes,
                    payload.caption.strip(),
                    is_story=True,
                )
    except (RuntimeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    async with AsyncSessionLocal() as session:
        upload_service = UploadService(session)
        upload = await upload_service.create(
            generation_output_id=generation_output_id,
            kind="story",
            caption=payload.caption.strip(),
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
        kind="story",
        instagram_post_id=post_id,
        posted_at=posted_at,
        account_username=instagram.username,
        generated_upload_id=upload.id,
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
