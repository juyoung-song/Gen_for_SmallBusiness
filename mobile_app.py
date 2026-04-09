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
from pathlib import Path
from typing import Literal

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
from schemas.image_schema import ImageGenerationRequest
from schemas.instagram_schema import (
    CaptionGenerationRequest,
    CaptionGenerationResponse,
)
from schemas.text_schema import TextGenerationRequest
from services.brand_image_service import BrandImageService
from services.caption_service import CaptionService
from services.image_service import ImageService, ImageServiceError
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


class MobileBootstrapResponse(BaseModel):
    onboarding_completed: bool
    brand: MobileBrandSummary | None = None
    image_backend_kind: str
    api_ready: bool
    instagram_ready: bool
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
    status: Literal["created", "existing"]
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


async def _load_bootstrap() -> MobileBootstrapResponse:
    async with AsyncSessionLocal() as session:
        brand_service = BrandImageService(session)
        product_service = ProductService(session)
        upload_service = UploadService(session)

        brand = await brand_service.get_for_user("default")
        products = await product_service.list_all()
        uploads = await upload_service.list_published()

    return MobileBootstrapResponse(
        onboarding_completed=brand is not None,
        brand=_serialize_brand(brand) if brand is not None else None,
        image_backend_kind=settings.IMAGE_BACKEND_KIND.value,
        api_ready=settings.is_api_ready,
        instagram_ready=settings.is_instagram_ready,
        product_count=len(products),
        published_reference_count=len(uploads),
    )


@app.get("/health")
async def health() -> dict:
    return {"ok": True, "image_backend_kind": settings.IMAGE_BACKEND_KIND.value}


@app.get("/api/mobile/bootstrap", response_model=MobileBootstrapResponse)
async def mobile_bootstrap() -> MobileBootstrapResponse:
    return await _load_bootstrap()


@app.post("/api/mobile/onboarding/complete", response_model=MobileOnboardingResponse)
async def complete_onboarding(
    payload: MobileOnboardingRequest,
) -> MobileOnboardingResponse:
    warnings: list[str] = []

    async with AsyncSessionLocal() as session:
        brand_service = BrandImageService(session)
        existing = await brand_service.get_for_user("default")
        if existing is not None:
            return MobileOnboardingResponse(
                status="existing",
                brand=_serialize_brand(existing),
            )

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
        created = await brand_service.create(
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

    return MobileOnboardingResponse(
        status="created",
        brand=_serialize_brand(created),
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


@app.get("/")
async def root() -> RedirectResponse:
    return RedirectResponse(url="/stitch/index.html", status_code=307)


app.mount("/mobile-assets", StaticFiles(directory=str(DATA_DIR)), name="mobile-assets")
app.mount("/stitch", StaticFiles(directory=str(STITCH_DIR), html=True), name="stitch")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("mobile_app:app", host="127.0.0.1", port=8007, reload=False)
