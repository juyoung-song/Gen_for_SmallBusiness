"""Mac 로컬 Instagram 캡처 워커.

내부 데모용 보조 서버:
- Mac에서 로그인된 Playwright persistent profile로 Instagram을 연다.
- VM mobile_app.py가 Cloudflare Tunnel을 통해 이 서버에 캡처를 요청한다.
- 응답은 data URL PNG 목록으로 반환한다.

운영용 Instagram 스크래퍼가 아니라, VM IP 429 회피를 위한 데모 전용 fallback이다.
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import os
from pathlib import Path
from typing import Annotated
from urllib.parse import urlparse

from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel, Field
from playwright.async_api import TimeoutError as PlaywrightTimeoutError
from playwright.async_api import async_playwright


PROFILE_DIR = Path(
    os.environ.get(
        "CAPTURE_WORKER_PROFILE_DIR",
        str(Path.home() / ".brewgram" / "instagram-capture-profile"),
    )
).expanduser()
TOKEN = os.environ.get("CAPTURE_WORKER_TOKEN", "")
HEADLESS = os.environ.get("CAPTURE_WORKER_HEADLESS", "1") not in {"0", "false", "False"}
USER_AGENT = os.environ.get("CAPTURE_WORKER_USER_AGENT", "")
VIEWPORT_WIDTH = int(os.environ.get("CAPTURE_WORKER_VIEWPORT_WIDTH", "1440"))
VIEWPORT_HEIGHT = int(os.environ.get("CAPTURE_WORKER_VIEWPORT_HEIGHT", "1200"))
SCROLL_AMOUNT = int(os.environ.get("CAPTURE_WORKER_SCROLL_AMOUNT", "900"))
TIMEOUT_MS = int(os.environ.get("CAPTURE_WORKER_TIMEOUT_MS", "45000"))


class CaptureRequest(BaseModel):
    url: str
    count: int = Field(default=2, ge=1, le=4)


class CapturedImage(BaseModel):
    name: str
    data_url: str


class CaptureResponse(BaseModel):
    status: str = "ok"
    images: list[CapturedImage]


app = FastAPI(title="Brewgram Instagram Capture Worker")


def _require_token(authorization: Annotated[str | None, Header()] = None) -> None:
    if not TOKEN:
        return
    expected = f"Bearer {TOKEN}"
    if authorization != expected:
        raise HTTPException(status_code=401, detail="Invalid capture worker token")


def _normalize_instagram_url(raw_url: str) -> str:
    cleaned = raw_url.strip()
    if not cleaned:
        raise HTTPException(status_code=400, detail="Instagram URL is required")
    if not cleaned.startswith(("http://", "https://")):
        cleaned = f"https://www.instagram.com/{cleaned.lstrip('@').strip('/')}/"

    parsed = urlparse(cleaned)
    host = parsed.netloc.lower()
    if host not in {"instagram.com", "www.instagram.com"}:
        raise HTTPException(status_code=400, detail="Only instagram.com URLs are allowed")
    return cleaned


def _detect_unusable_page(current_url: str, body_text: str) -> str | None:
    normalized_url = current_url.lower()
    normalized_text = body_text.lower()
    if "accounts/login" in normalized_url:
        return "Instagram login page is shown. Open the worker profile and log in first."
    if "http error 429" in normalized_text:
        return "Instagram returned HTTP ERROR 429 from this Mac session."
    if "this page isn" in normalized_text and "working" in normalized_text:
        return "Instagram error page is shown instead of the profile."
    return None


async def _capture(url: str, count: int) -> list[CapturedImage]:
    PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    launch_kwargs = {
        "headless": HEADLESS,
        "viewport": {"width": VIEWPORT_WIDTH, "height": VIEWPORT_HEIGHT},
        "locale": "ko-KR",
        "timezone_id": "Asia/Seoul",
    }
    if USER_AGENT:
        launch_kwargs["user_agent"] = USER_AGENT

    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context(
            str(PROFILE_DIR),
            **launch_kwargs,
        )
        try:
            page = context.pages[0] if context.pages else await context.new_page()
            page.set_default_timeout(TIMEOUT_MS)
            await page.goto(url, wait_until="domcontentloaded", timeout=TIMEOUT_MS)
            await page.wait_for_timeout(2500)

            try:
                body_text = await page.locator("body").inner_text(timeout=5000)
            except PlaywrightTimeoutError:
                body_text = ""
            reason = _detect_unusable_page(page.url, body_text)
            if reason:
                raise HTTPException(status_code=502, detail=reason)

            images: list[CapturedImage] = []
            for idx in range(1, count + 1):
                png = await page.screenshot(full_page=False, type="png")
                encoded = base64.b64encode(png).decode("ascii")
                images.append(
                    CapturedImage(
                        name=f"instagram_capture_{idx}.png",
                        data_url=f"data:image/png;base64,{encoded}",
                    )
                )
                if idx < count:
                    await page.mouse.wheel(0, SCROLL_AMOUNT)
                    await page.wait_for_timeout(1500)
            return images
        finally:
            await context.close()


@app.get("/health")
async def health() -> dict:
    return {
        "ok": True,
        "headless": HEADLESS,
        "profile_dir": str(PROFILE_DIR),
    }


@app.post("/capture", response_model=CaptureResponse, dependencies=[Depends(_require_token)])
async def capture(payload: CaptureRequest) -> CaptureResponse:
    url = _normalize_instagram_url(payload.url)
    images = await _capture(url, payload.count)
    return CaptureResponse(images=images)


async def _open_login() -> None:
    PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context(
            str(PROFILE_DIR),
            headless=False,
            viewport={"width": VIEWPORT_WIDTH, "height": VIEWPORT_HEIGHT},
            locale="ko-KR",
            timezone_id="Asia/Seoul",
        )
        page = context.pages[0] if context.pages else await context.new_page()
        await page.goto("https://www.instagram.com/accounts/login/")
        print(f"Opened Instagram login with profile: {PROFILE_DIR}")
        print("Log in manually, then press Enter here to close the browser.")
        await asyncio.to_thread(input)
        await context.close()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["login"])
    args = parser.parse_args()
    if args.command == "login":
        asyncio.run(_open_login())


if __name__ == "__main__":
    main()
