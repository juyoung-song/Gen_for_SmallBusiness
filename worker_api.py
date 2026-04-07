"""GCP VM에서 실행하는 이미지 생성 워커 API."""

import base64
import secrets

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

from config.settings import get_settings, setup_logging
from schemas.image_schema import ImageGenerationRequest, ImageInferenceOptions
from services.image_service import ImageService, ImageServiceError


class WorkerImageRequest(BaseModel):
    """원격 워커 입력 페이로드."""

    prompt: str = Field(default="")
    product_name: str = Field(default="")
    description: str = Field(default="")
    brand_philosophy: str = Field(default="")
    goal: str = Field(default="일반 홍보")
    style: str = Field(default="기본")
    is_new_product: bool = Field(default=False)
    is_renewal_product: bool = Field(default=False)
    attachment_count: int = Field(default=0)
    reference_analysis: str = Field(default="")
    image_data_b64: str | None = Field(default=None)
    inference_options: ImageInferenceOptions | None = Field(default=None)


class WorkerImageResponse(BaseModel):
    """원격 워커 출력 페이로드."""

    image_data_b64: str
    revised_prompt: str = ""


settings = get_settings()
setup_logging(settings)

if settings.IMAGE_BACKEND.lower() == "remote":
    raise RuntimeError(
        "worker_api.py는 IMAGE_BACKEND=remote 상태로 실행할 수 없습니다. "
        "VM 워커에서는 USE_LOCAL_MODEL=true 또는 기본 HF 모드를 사용하세요."
    )

if not settings.IMAGE_WORKER_TOKEN:
    raise RuntimeError(
        "IMAGE_WORKER_TOKEN이 설정되지 않았습니다. VM의 .env에 토큰을 넣어주세요."
    )

app = FastAPI(title="Gen for SmallBusiness Image Worker")
image_service = ImageService(settings)


def _check_auth(authorization: str | None) -> None:
    expected = f"Bearer {settings.IMAGE_WORKER_TOKEN}"
    if not authorization or not secrets.compare_digest(authorization, expected):
        raise HTTPException(status_code=401, detail="Unauthorized")


@app.get("/health")
def health() -> dict:
    """워커 기동 상태 확인."""
    return {
        "ok": True,
        "use_local_model": settings.USE_LOCAL_MODEL,
        "image_model": settings.IMAGE_MODEL,
        "backend": settings.LOCAL_BACKEND if settings.USE_LOCAL_MODEL else "hf",
    }


@app.post("/generate-image", response_model=WorkerImageResponse)
def generate_image(
    payload: WorkerImageRequest,
    authorization: str | None = Header(default=None),
) -> WorkerImageResponse:
    """이미지 생성 요청을 처리한다."""
    _check_auth(authorization)

    image_data = (
        base64.b64decode(payload.image_data_b64)
        if payload.image_data_b64
        else None
    )
    request = ImageGenerationRequest(
        prompt=payload.prompt,
        product_name=payload.product_name,
        description=payload.description,
        brand_philosophy=payload.brand_philosophy,
        goal=payload.goal,
        style=payload.style,
        is_new_product=payload.is_new_product,
        is_renewal_product=payload.is_renewal_product,
        attachment_count=payload.attachment_count,
        reference_analysis=payload.reference_analysis,
        image_data=image_data,
        inference_options=payload.inference_options,
    )

    try:
        result = image_service.generate_ad_image(request)
    except ImageServiceError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    return WorkerImageResponse(
        image_data_b64=base64.b64encode(result.image_data).decode("utf-8"),
        revised_prompt=result.revised_prompt,
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "worker_api:app",
        host=settings.IMAGE_WORKER_HOST,
        port=settings.IMAGE_WORKER_PORT,
        reload=False,
    )
