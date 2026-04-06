# Plan

코드 리뷰에서 도출된 이슈들을 우선순위별로 정리한 수정 계획.

---

## Critical

### C-1. FreeImage.host API 키 하드코딩 제거
- **파일**: `services/instagram_service.py` (62번째 줄)
- **문제**: `"key": "6d207e02198a847aa98d0a2a901485a5"` 가 소스코드에 직접 노출됨
- **해결**: `.env`에 `FREEIMAGE_API_KEY=...` 추가, `config/settings.py`의 `Settings` 클래스에 필드 추가, 서비스에서 `settings.FREEIMAGE_API_KEY`로 참조

### C-2. `run_async()` else 분기 버그
- **파일**: `app.py` (134~140번째 줄)
- **문제**: `try/except` 두 분기 모두 `asyncio.run(coro)` 호출 → 실행 중인 이벤트 루프에서 충돌
- **해결**: `else` 분기에서 `loop.run_until_complete(coro)` 사용, 또는 `nest_asyncio` 패키지 도입

### C-3. `requests` 라이브러리 미선언
- **파일**: `services/instagram_service.py` (6번째 줄)
- **문제**: `import requests` 사용 중이나 `pyproject.toml`, `requirements.txt` 어디에도 미선언
- **해결**: `instagram_service.py`를 `httpx`로 통일하거나, `requests`를 의존성에 명시

---

## Important

### I-1. `TEXT_MODEL` 기본값 오탈자
- **파일**: `config/settings.py` (41번째 줄)
- **문제**: `TEXT_MODEL: str = "gpt-5-mini"` — 존재하지 않는 모델명
- **해결**: `"gpt-4o-mini"` 또는 `"gpt-4.1-mini"` 등 유효한 모델명으로 수정

### I-2. `CaptionService` Mock 모드 분기 누락
- **파일**: `services/caption_service.py`
- **문제**: `USE_MOCK=true` 상태에서 인스타 캡션 버튼 클릭 시 실제 OpenAI API 호출 시도 → 인증 오류
- **해결**: `TextService`, `ImageService`와 동일하게 `_mock_response()` / `_api_response()` 분기 추가

### I-3. `_parse_response()` 내부 반복 import
- **파일**: `services/text_service.py` (271~272번째 줄)
- **문제**: 함수 호출마다 `import re`, `import logging` 실행 (logging은 파일 상단에 이미 있어 중복)
- **해결**: 파일 상단으로 import 이동

### I-4. `compose_story_image()` bare `except` 및 macOS 전용 폰트 경로
- **파일**: `services/image_service.py` (252번째 줄)
- **문제**: bare `except:` 가 `SystemExit`, `KeyboardInterrupt`까지 삼킴. 폰트 경로가 macOS `/System/Library/Fonts/...` 하드코딩
- **해결**: `except Exception:` 으로 변경. 폰트 경로를 `Settings` 또는 환경변수로 분리

### I-5. `@lru_cache` Settings `.env` 변경 미반영
- **파일**: `config/settings.py` (84번째 줄)
- **문제**: `@lru_cache`로 캐싱된 `get_settings()` → 테스트/재시작 없이 `.env` 변경 미반영
- **해결**: `@st.cache_resource` 사용 고려 또는 `lru_cache` 사용 시 주의사항 문서화

---

## Suggestions

### S-1. `DB_DIR` 상대경로 → 절대경로
- **파일**: `config/database.py` (12번째 줄), `services/history_service.py`
- **문제**: `"./data"` 상대경로는 실행 디렉토리에 따라 달라질 수 있음
- **해결**: `pathlib.Path(__file__).parent.parent / "data"` 형태로 변경

### S-2. 인스타 업로드 진행률 범위 초과 방지
- **파일**: `app.py` (252~269번째 줄)
- **문제**: `idx += 0.2` 방식에서 generator가 5단계 초과 시 `st.progress()` 범위(`[0, 1]`) 초과
- **해결**: `st.progress(min(idx, 1.0))`으로 클램핑

### S-3. `TONE_DISPLAY_MAP` / `STYLE_DISPLAY_MAP` 중복 제거
- **파일**: `app.py` (172~185번째 줄)
- **문제**: 두 딕셔너리가 동일한 키-값 쌍
- **해결**: 하나로 통합하여 텍스트/이미지 양쪽에서 재사용

---

## Feature: 로컬 IP-Adapter + SD 1.5 이미지 생성

**목표**: 사용자 업로드 사진을 실제로 이미지 생성 AI에 반영. 현재는 `has_reference` 플래그만 존재하고 이미지 픽셀이 미전달됨.

**아키텍처**: `models/` 디렉토리에 모델별 파일 분리. `ImageService`는 `LocalImageBackend` 프로토콜만 바라보며, 모델 파일은 교체·추가 가능.

```
models/
  local_backend.py     # LocalImageBackend 프로토콜 (인터페이스 정의)
  sd15.py              # SD 1.5 txt2img (참조 이미지 없을 때 fallback)
  ip_adapter.py        # IP-Adapter + SD 1.5 (참조 이미지 있을 때 사용)
services/
  image_service.py     # _local_response() 분기 추가
config/
  settings.py          # LOCAL_MODEL_CACHE_DIR, USE_LOCAL_MODEL 설정 추가
```

---

### Task 1: `LocalImageBackend` 프로토콜 정의

**파일**: `models/local_backend.py` (신규)

```python
# models/local_backend.py
from typing import Protocol
from schemas.image_schema import ImageGenerationRequest, ImageGenerationResponse

class LocalImageBackend(Protocol):
    def generate(self, request: ImageGenerationRequest) -> ImageGenerationResponse:
        ...

    def is_available(self) -> bool:
        """모델/어댑터 파일이 로컬에 존재하는지 확인."""
        ...
```

---

### Task 2: Settings에 로컬 모델 설정 추가

**파일**: `config/settings.py`

`Settings` 클래스에 필드 추가:

```python
# ── Local Model Settings ──
USE_LOCAL_MODEL: bool = False
LOCAL_MODEL_CACHE_DIR: str = "./models/cache"
LOCAL_SD15_MODEL_ID: str = "runwayml/stable-diffusion-v1-5"
LOCAL_IP_ADAPTER_ID: str = "h94/IP-Adapter"
LOCAL_IP_ADAPTER_SUBFOLDER: str = "models"
LOCAL_IP_ADAPTER_WEIGHT_NAME: str = "ip-adapter_sd15.bin"
LOCAL_INFERENCE_STEPS: int = 30
LOCAL_GUIDANCE_SCALE: float = 7.5
LOCAL_IP_ADAPTER_SCALE: float = 0.6  # 참조 이미지 반영 강도 (0~1)
```

`.env`에도 추가:
```env
USE_LOCAL_MODEL=false
LOCAL_MODEL_CACHE_DIR=./models/cache
```

---

### Task 3: SD 1.5 백엔드 구현

**파일**: `models/sd15.py` (신규)

- 참조 이미지 없을 때 사용하는 순수 txt2img
- `StableDiffusionPipeline` (diffusers) + MPS 백엔드
- 첫 호출 시 모델 lazy 로드, 이후 재사용

```python
# models/sd15.py
import io
import logging
import torch
from pathlib import Path
from PIL import Image
from diffusers import StableDiffusionPipeline

from config.settings import Settings
from models.local_backend import LocalImageBackend
from schemas.image_schema import ImageGenerationRequest, ImageGenerationResponse

logger = logging.getLogger(__name__)

class SD15Backend:
    """SD 1.5 txt2img 로컬 백엔드."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._pipe: StableDiffusionPipeline | None = None

    def is_available(self) -> bool:
        try:
            import diffusers  # noqa: F401
            return True
        except ImportError:
            return False

    @property
    def pipe(self) -> StableDiffusionPipeline:
        if self._pipe is None:
            cache_dir = Path(self.settings.LOCAL_MODEL_CACHE_DIR)
            cache_dir.mkdir(parents=True, exist_ok=True)
            device = "mps" if torch.backends.mps.is_available() else "cpu"
            logger.info("SD 1.5 모델 로딩 (device=%s)...", device)
            self._pipe = StableDiffusionPipeline.from_pretrained(
                self.settings.LOCAL_SD15_MODEL_ID,
                torch_dtype=torch.float16 if device == "mps" else torch.float32,
                cache_dir=str(cache_dir),
            ).to(device)
            self._pipe.enable_attention_slicing()
        return self._pipe

    def generate(self, request: ImageGenerationRequest) -> ImageGenerationResponse:
        result = self.pipe(
            prompt=request.prompt,
            num_inference_steps=self.settings.LOCAL_INFERENCE_STEPS,
            guidance_scale=self.settings.LOCAL_GUIDANCE_SCALE,
        )
        image: Image.Image = result.images[0]
        buf = io.BytesIO()
        image.save(buf, format="PNG")
        return ImageGenerationResponse(
            image_data=buf.getvalue(),
            revised_prompt=request.prompt,
        )
```

---

### Task 4: IP-Adapter 백엔드 구현

**파일**: `models/ip_adapter.py` (신규)

- 참조 이미지가 있을 때 사용
- `StableDiffusionPipeline` + `load_ip_adapter()` (diffusers 0.24+)
- `request.image_data` (bytes) → PIL Image → IP-Adapter에 전달

```python
# models/ip_adapter.py
import io
import logging
import torch
from pathlib import Path
from PIL import Image
from diffusers import StableDiffusionPipeline

from config.settings import Settings
from schemas.image_schema import ImageGenerationRequest, ImageGenerationResponse

logger = logging.getLogger(__name__)

class IPAdapterBackend:
    """IP-Adapter + SD 1.5 로컬 백엔드. 참조 이미지의 스타일을 반영해 생성."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._pipe: StableDiffusionPipeline | None = None

    def is_available(self) -> bool:
        try:
            import diffusers  # noqa: F401
            return True
        except ImportError:
            return False

    @property
    def pipe(self) -> StableDiffusionPipeline:
        if self._pipe is None:
            cache_dir = Path(self.settings.LOCAL_MODEL_CACHE_DIR)
            cache_dir.mkdir(parents=True, exist_ok=True)
            device = "mps" if torch.backends.mps.is_available() else "cpu"
            logger.info("IP-Adapter 모델 로딩 (device=%s)...", device)
            pipe = StableDiffusionPipeline.from_pretrained(
                self.settings.LOCAL_SD15_MODEL_ID,
                torch_dtype=torch.float16 if device == "mps" else torch.float32,
                cache_dir=str(cache_dir),
            ).to(device)
            pipe.load_ip_adapter(
                self.settings.LOCAL_IP_ADAPTER_ID,
                subfolder=self.settings.LOCAL_IP_ADAPTER_SUBFOLDER,
                weight_name=self.settings.LOCAL_IP_ADAPTER_WEIGHT_NAME,
                cache_dir=str(cache_dir),
            )
            pipe.set_ip_adapter_scale(self.settings.LOCAL_IP_ADAPTER_SCALE)
            pipe.enable_attention_slicing()
            self._pipe = pipe
        return self._pipe

    def generate(self, request: ImageGenerationRequest) -> ImageGenerationResponse:
        ref_image: Image.Image | None = None
        if request.image_data:
            ref_image = Image.open(io.BytesIO(request.image_data)).convert("RGB")

        result = self.pipe(
            prompt=request.prompt,
            ip_adapter_image=ref_image,
            num_inference_steps=self.settings.LOCAL_INFERENCE_STEPS,
            guidance_scale=self.settings.LOCAL_GUIDANCE_SCALE,
        )
        image: Image.Image = result.images[0]
        buf = io.BytesIO()
        image.save(buf, format="PNG")
        return ImageGenerationResponse(
            image_data=buf.getvalue(),
            revised_prompt=request.prompt,
        )
```

---

### Task 5: `ImageService`에 `_local_response()` 분기 추가

**파일**: `services/image_service.py`

`generate_ad_image()` 분기 수정:

```python
def generate_ad_image(self, request: ImageGenerationRequest) -> ImageGenerationResponse:
    if self.settings.USE_MOCK:
        return self._mock_response(request)
    if self.settings.USE_LOCAL_MODEL:
        return self._local_response(request)
    return self._api_response(request)
```

`_local_response()` 메서드 추가:

```python
def _local_response(self, request: ImageGenerationRequest) -> ImageGenerationResponse:
    """로컬 diffusers 모델로 이미지 생성. 참조 이미지 유무에 따라 백엔드 자동 선택."""
    from models.ip_adapter import IPAdapterBackend
    from models.sd15 import SD15Backend

    # GPT로 한글 프롬프트 → 영어 번역 (기존 로직 재사용)
    raw_prompt = build_image_prompt(
        product_name=request.product_name,
        description=request.description,
        style=request.style,
        goal=request.goal,
        ad_copy=request.prompt,
        has_reference=(request.image_data is not None),
    )
    translation = self.client.chat.completions.create(
        model=self.settings.TEXT_MODEL,
        messages=[
            {"role": "system", "content": "Translate and enhance the given Korean description into a highly detailed English prompt for Stable Diffusion. Output ONLY the English prompt, no extra text."},
            {"role": "user", "content": raw_prompt},
        ],
        timeout=self.settings.TEXT_TIMEOUT,
    )
    english_prompt = translation.choices[0].message.content.strip()

    # 참조 이미지 있으면 IP-Adapter, 없으면 SD 1.5
    if request.image_data:
        backend = IPAdapterBackend(self.settings)
    else:
        backend = SD15Backend(self.settings)

    if not backend.is_available():
        raise ImageServiceError(
            "로컬 모델 실행에 필요한 'diffusers' 패키지가 설치되지 않았습니다. "
            "`pip install diffusers transformers accelerate` 를 실행해주세요."
        )

    translated_request = request.model_copy(update={"prompt": english_prompt})
    logger.info("로컬 추론 시작 (backend=%s, prompt=%s)", type(backend).__name__, english_prompt[:60])
    return backend.generate(translated_request)
```

---

### Task 6: 의존성 추가

**파일**: `pyproject.toml`, `requirements.txt`

`pyproject.toml`에 추가:
```toml
"diffusers>=0.24.0",
"transformers>=4.35.0",
"accelerate>=0.24.0",
"torch>=2.1.0",
```

설치 명령:
```bash
uv add diffusers transformers accelerate torch
# 또는
pip install diffusers>=0.24.0 transformers>=4.35.0 accelerate>=0.24.0 torch>=2.1.0
```

---

### Task 7: `.env` 설정 및 첫 실행 검증

`.env`에서 로컬 모드 활성화:
```env
USE_LOCAL_MODEL=true
USE_MOCK=false
LOCAL_MODEL_CACHE_DIR=./models/cache
LOCAL_INFERENCE_STEPS=20        # 첫 테스트는 빠른 확인용으로 낮춤
LOCAL_IP_ADAPTER_SCALE=0.6
```

첫 실행 시 모델 자동 다운로드 (~2.3GB). 이후 `./models/cache`에 캐시됨.

---

## 런타임 오류 해결 이력 (2026-04-03)

### 호환성 문제로 인한 버전 고정
1. **torchvision 누락** → `CLIPImageProcessorPil` fallback이 tuple 반환 → `uv add torchvision>=0.26.0`으로 해결
2. **transformers 5.x `@can_return_tuple`** → `CLIPVisionModelWithProjection.forward()`가 tuple 반환, diffusers 0.37.1 미대응 → `transformers>=4.44.0,<5.0.0`으로 고정
3. **diffusers 0.37.1 + transformers 4.x 불일치** → `Dinov2WithRegistersConfig` import 실패 → `diffusers==0.31.0`으로 다운그레이드
4. **`enable_attention_slicing()` + IP-Adapter 충돌** → IP-Adapter attention processor가 `SlicedAttnProcessor`로 교체되며 `encoder_hidden_states.shape` 오류 → `enable_attention_slicing()` 제거

### 남은 과제: 참조 이미지 반영 강도
- IP-Adapter scale=0.6 설정이나 생성 결과가 참조 이미지를 충분히 반영하지 않음
- 개선 옵션:
  - `LOCAL_IP_ADAPTER_SCALE` 0.8~1.0으로 상향 테스트
  - `ip-adapter-plus_sd15.bin` (더 강한 스타일 반영) 전환 검토
  - 장기: SDXL + IP-Adapter SDXL 전환 (품질·반영도 모두 향상)
