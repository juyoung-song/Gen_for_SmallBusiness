# Checklist

코드 리뷰 수정 작업 체크리스트. 우선순위 순으로 진행.

---

## Critical

- [ ] **C-1** FreeImage API 키 `.env`로 이동 (`services/instagram_service.py`)
- [ ] **C-2** `run_async()` else 분기 버그 수정 (`app.py:134`)
- [ ] **C-3** `requests` 의존성 선언 또는 `httpx`로 교체 (`services/instagram_service.py`)

## Important

- [ ] **I-1** `TEXT_MODEL` 기본값 수정: `"gpt-5-mini"` → 유효한 모델명 (`config/settings.py:41`)
- [ ] **I-2** `CaptionService` Mock 분기 추가 (`services/caption_service.py`)
- [ ] **I-3** `_parse_response()` 내부 import를 파일 상단으로 이동 (`services/text_service.py:271`)
- [ ] **I-4** `compose_story_image()` bare `except` 수정 + 폰트 경로 분리 (`services/image_service.py:252`)
- [ ] **I-5** `get_settings()` 캐싱 전략 검토 (`config/settings.py:84`)

## Suggestions

- [ ] **S-1** `DB_DIR` 상대경로 → `pathlib` 절대경로 (`config/database.py`)
- [ ] **S-2** 인스타 업로드 진행률 `min(idx, 1.0)` 클램핑 (`app.py:252`)
- [ ] **S-3** `TONE_DISPLAY_MAP` / `STYLE_DISPLAY_MAP` 중복 제거 (`app.py:172`)

---

## Feature: 로컬 IP-Adapter + SD 1.5

- [x] **F-1** `models/local_backend.py` — `LocalImageBackend` 프로토콜 정의
- [x] **F-2** `config/settings.py` — `USE_LOCAL_MODEL`, `LOCAL_MODEL_CACHE_DIR` 등 설정 필드 추가
- [x] **F-3** `models/sd15.py` — SD 1.5 txt2img 백엔드 구현
- [x] **F-4** `models/ip_adapter.py` — IP-Adapter + SD 1.5 백엔드 구현
- [x] **F-5** `services/image_service.py` — `_local_response()` 분기 추가, `generate_ad_image()` 수정
- [x] **F-6** `pyproject.toml` / `requirements.txt` — `diffusers`, `transformers`, `accelerate`, `torch` 추가
- [x] **F-7** `.env` 로컬 모델 설정 추가 및 import/Settings 로드 검증 완료
- [x] **F-8** 패키지 실제 설치 및 첫 추론 실행 검증 — 설치 완료, 런타임 오류 해결 중
- [ ] **F-9** 참조 이미지 반영 강도 개선 검토 (scale 상향 / SDXL IP-Adapter / ControlNet)
