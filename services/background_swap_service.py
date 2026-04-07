"""배경 교체 서비스.

두 가지 방식 비교:
A. prompt_only  — 원본 이미지 + "배경만 바꿔라" 프롬프트로 HF img2img 호출
B. rembg        — rembg 누끼 → HF txt2img 배경 생성 → Pillow 합성
"""

import io
import logging

import httpx
from PIL import Image

from config.settings import Settings

logger = logging.getLogger(__name__)


class BackgroundSwapError(Exception):
    """배경 교체 서비스 에러."""


# 스타일별 배경 프롬프트 힌트
_STYLE_BG_MAP: dict[str, str] = {
    "기본": "clean white studio background, soft neutral tones, minimal",
    "감성": "warm bokeh background, soft golden hour light, cozy aesthetic, pastel tones",
    "고급": "dark luxury background, elegant marble surface, moody dramatic lighting",
    "유머": "bright colorful background, playful patterns, vibrant cheerful colors",
    "심플": "plain solid color background, flat lay, minimalist composition",
}

_GOAL_BG_MAP: dict[str, str] = {
    "신상품 홍보": "fresh modern atmosphere, spotlight on product, launch energy",
    "할인 행사": "vibrant energetic mood, promotional atmosphere",
    "매장 소개": "inviting cozy interior ambiance, professional setting",
    "시즌 홍보": "seasonal thematic atmosphere, natural seasonal elements",
    "일반 홍보": "commercial product photography setting",
}


def _build_background_prompt(
    product_name: str,
    style: str,
    goal: str,
    extra_hint: str = "",
) -> str:
    style_hint = _STYLE_BG_MAP.get(style, _STYLE_BG_MAP["기본"])
    goal_hint = _GOAL_BG_MAP.get(goal, _GOAL_BG_MAP["일반 홍보"])
    prompt = (
        f"A professional commercial advertisement background for '{product_name}' product photography. "
        f"{style_hint}. {goal_hint}. "
        "No product in the image, background only. "
        "High resolution, cinematic quality, photorealistic, no text."
    )
    if extra_hint:
        prompt += f" Additional mood: {extra_hint}."
    return prompt


def _build_prompt_only_prompt(
    product_name: str,
    style: str,
    goal: str,
    extra_hint: str = "",
) -> str:
    style_hint = _STYLE_BG_MAP.get(style, _STYLE_BG_MAP["기본"])
    goal_hint = _GOAL_BG_MAP.get(goal, _GOAL_BG_MAP["일반 홍보"])
    prompt = (
        f"Keep the product '{product_name}' exactly as-is. "
        f"Replace only the background with: {style_hint}. "
        f"{goal_hint}. "
        "Product must remain unchanged, same position, same lighting on product. "
        "High resolution, commercial product photography, no text."
    )
    if extra_hint:
        prompt += f" Background mood: {extra_hint}."
    return prompt


def _call_hf_api(
    prompt: str,
    model_id: str,
    hf_api_key: str,
    timeout: float,
    image_bytes: bytes | None = None,
) -> bytes:
    """HF Inference API 호출. image_bytes 있으면 img2img, 없으면 txt2img."""
    api_url = f"https://router.huggingface.co/hf-inference/models/{model_id}"
    headers = {"Authorization": f"Bearer {hf_api_key}"}

    if image_bytes:
        # img2img: multipart form으로 전송
        import base64
        payload = {
            "inputs": prompt,
            "parameters": {"image": base64.b64encode(image_bytes).decode()},
        }
    else:
        payload = {"inputs": prompt}

    logger.info("HF API 호출 (model=%s, img2img=%s)", model_id, image_bytes is not None)
    try:
        response = httpx.post(api_url, headers=headers, json=payload, timeout=timeout)
        response.raise_for_status()
    except httpx.HTTPStatusError as e:
        raise BackgroundSwapError(f"HF API 오류 ({e.response.status_code}): {e.response.text}")
    except httpx.TimeoutException:
        raise BackgroundSwapError(f"HF API 타임아웃 ({timeout}초)")

    return response.content


def _remove_background(image_bytes: bytes) -> Image.Image:
    try:
        from rembg import remove
    except ImportError:
        raise BackgroundSwapError("rembg가 설치되지 않았습니다. `uv add rembg`로 설치해주세요.")

    logger.info("배경 제거 시작...")
    result = remove(image_bytes)
    if isinstance(result, Image.Image):
        img = result.convert("RGBA")
    else:
        img = Image.open(io.BytesIO(bytes(result))).convert("RGBA")
    logger.info("배경 제거 완료 (size=%s)", img.size)
    return img


def _composite(product_rgba: Image.Image, background_bytes: bytes) -> bytes:
    bg = Image.open(io.BytesIO(background_bytes)).convert("RGBA")
    bg = bg.resize(product_rgba.size, Image.Resampling.LANCZOS)

    bg_w, bg_h = bg.size
    prod_w, prod_h = product_rgba.size
    max_w, max_h = int(bg_w * 0.80), int(bg_h * 0.80)
    scale = min(max_w / prod_w, max_h / prod_h, 1.0)
    new_w, new_h = int(prod_w * scale), int(prod_h * scale)
    product_resized = product_rgba.resize((new_w, new_h), Image.Resampling.LANCZOS)

    paste_x = (bg_w - new_w) // 2
    paste_y = bg_h - new_h - int(bg_h * 0.05)

    result = bg.copy()
    result.paste(product_resized, (paste_x, paste_y), mask=product_resized)
    buf = io.BytesIO()
    result.convert("RGB").save(buf, format="PNG")
    return buf.getvalue()


class BackgroundSwapService:
    """배경 교체 서비스 — rembg 누끼 / prompt_only / rembg+합성 세 방식 제공."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def _check_hf(self) -> None:
        if not self.settings.HUGGINGFACE_API_KEY:
            raise BackgroundSwapError("HUGGINGFACE_API_KEY가 설정되지 않았습니다.")

    def extract_subject(self, image_bytes: bytes) -> bytes:
        """누끼만 따서 PNG bytes 반환 (배경 생성 없음)."""
        img = _remove_background(image_bytes)
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()

    def swap_with_prompt(
        self,
        subject_rgba_bytes: bytes,
        prompt: str,
        model_id: str | None = None,
        output_size: tuple[int, int] = (1024, 1024),
    ) -> bytes:
        """누끼 이미지 + 사용자 프롬프트 → HF txt2img 배경 생성 → 합성."""
        self._check_hf()
        bg_model = model_id or self.settings.IMAGE_MODEL
        logger.info("프롬프트 기반 배경 생성 (model=%s, prompt=%s...)", bg_model, prompt[:60])
        bg_bytes = _call_hf_api(
            prompt=prompt,
            model_id=bg_model,
            hf_api_key=self.settings.HUGGINGFACE_API_KEY,
            timeout=self.settings.IMAGE_TIMEOUT,
        )
        subject_rgba = Image.open(io.BytesIO(subject_rgba_bytes)).convert("RGBA")
        subject_rgba = subject_rgba.resize(output_size, Image.Resampling.LANCZOS)
        return _composite(subject_rgba, bg_bytes)

    def swap_prompt_only(
        self,
        product_image_bytes: bytes,
        style: str = "기본",
        goal: str = "일반 홍보",
        product_name: str = "",
        extra_hint: str = "",
        model_id: str | None = None,
    ) -> bytes:
        """방식 A: 원본 이미지 + 프롬프트로 HF img2img 호출. 배경만 바꾸도록 지시."""
        self._check_hf()
        prompt = _build_prompt_only_prompt(product_name, style, goal, extra_hint)
        bg_model = model_id or self.settings.IMAGE_MODEL
        logger.info("방식 A (prompt_only) 시작")
        result = _call_hf_api(
            prompt=prompt,
            model_id=bg_model,
            hf_api_key=self.settings.HUGGINGFACE_API_KEY,
            timeout=self.settings.IMAGE_TIMEOUT,
            image_bytes=product_image_bytes,
        )
        return result

    def swap_rembg(
        self,
        product_image_bytes: bytes,
        style: str = "기본",
        goal: str = "일반 홍보",
        product_name: str = "",
        extra_hint: str = "",
        model_id: str | None = None,
    ) -> bytes:
        """방식 B: rembg 누끼 → HF txt2img 배경 생성 → Pillow 합성."""
        self._check_hf()

        # 1. 누끼
        product_rgba = _remove_background(product_image_bytes)

        # 2. 배경 생성
        prompt = _build_background_prompt(product_name, style, goal, extra_hint)
        bg_model = model_id or self.settings.IMAGE_MODEL
        logger.info("방식 B (rembg) 배경 생성 시작")
        bg_bytes = _call_hf_api(
            prompt=prompt,
            model_id=bg_model,
            hf_api_key=self.settings.HUGGINGFACE_API_KEY,
            timeout=self.settings.IMAGE_TIMEOUT,
        )

        # 3. 합성
        logger.info("상품 + 배경 합성 중...")
        return _composite(product_rgba, bg_bytes)
