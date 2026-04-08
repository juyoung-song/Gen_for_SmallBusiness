# Checklist

> **작성일:** 2026-04-08
> **마지막 갱신:** 2026-04-08 (Phase 1 완료)
> **베이스:** [`plan.md`](plan.md)
> 작업 단위 = 한 줄. 끝내는 즉시 체크. 대부분 1커밋 = 1체크.
>
> **TDD 정책 (2026-04-08 추가):** Step 1.2 부터 모든 신규 production 코드는
> RED → GREEN → REFACTOR 사이클로 작성한다. 단, Step 1.1 (이동/이름 변경 위주)은
> 사이클 도입 전 작성되어 회귀 검증만 수행.

---

## Phase 1 — 리팩터링

### Step 1.1 — `backends/` 신설 ✅ (2026-04-08, 커밋 c69586a)

- [x] **1.1.1** `backends/__init__.py` 생성
- [x] **1.1.2** `backends/image_base.py` — `ImageBackend` 프로토콜 작성
- [x] **1.1.3** `backends/text_base.py` — `TextBackend` 프로토콜 작성
- [x] **1.1.4** `models/sd15.py` → `backends/hf_sd15.py` 이동 (HFSD15Backend, name="hf_sd15")
- [x] **1.1.5** `models/ip_adapter.py` → `backends/hf_ip_adapter.py` 이동
- [x] **1.1.6** `models/img2img.py` → `backends/hf_img2img.py` 이동
- [x] **1.1.7** `models/hybrid.py` → `backends/hf_hybrid.py` 이동
- [x] **1.1.8** `models/local_backend.py` 삭제 (역할이 image_base로 흡수됨)
- [x] **1.1.9** `backends/openai_gpt.py` + `backends/hf_inference_api.py` 신규 (text_service / image_service 의 API 호출 로직 추출)
- [x] **1.1.10** `backends/remote_worker.py` 신규
- [x] **1.1.11** `backends/mock_image.py` / `backends/mock_text.py` 신규
- [x] **1.1.12** `backends/registry.py` — 환경 변수 기반 백엔드 선택 팩토리
- [x] **1.1.13** import 경로 일괄 수정 (services, app.py, worker_api.py, README.md)
- [x] **1.1.14** Streamlit 앱 정상 기동 검증 (`python -c "import app"`)
- [x] **1.1.15** 커밋: `refactor(Step 1.1): backends/ 디렉토리 신설 및 백엔드 분리`

**Step 1.1 회고:**
- TDD 도입 전이라 회귀 검증만 수행 (import 검증). Phase 1 종료 시 backends 회귀 테스트 보강 필요.
- 본래 Step 1.3 으로 분리되어 있던 작업 일부가 Step 1.1 안으로 들어옴:
  - 1.3.1 (image_service.py 분기 제거 → registry 호출): **완료**
  - 1.3.2 (text_service.py 동일 패턴): **완료**
  - 1.3.3 (text_service `import re` 파일 상단 이동): openai_gpt.py 작성하면서 자연스럽게 처리됨
  - 추가로 image_service 의 한국어→영문 번역을 서비스의 단일 책임으로 통합
- 이로 인해 Step 1.3 의 잔여 작업은 코드 리뷰 지적사항(C-1, I-1, I-2, I-4, I-5)에 한정됨

### Step 1.2 — ORM 재설계 (TDD)

**사전 인프라:**
- [x] **1.2.0a** pytest + pytest-asyncio 의존성 추가 (dev group)
- [x] **1.2.0b** `tests/`, `tests/test_models/`, `tests/test_services/` 디렉토리 생성
- [x] **1.2.0c** `tests/conftest.py` — 인메모리 SQLite + async 세션 fixture, SQLite FK PRAGMA 활성화
- [x] **1.2.0d** `pyproject.toml` `[tool.pytest.ini_options]` 추가 (asyncio mode=auto)

**ORM 모델 (RED → GREEN):**
- [x] **1.2.1** `tests/test_models/test_brand_image.py` 작성 → RED 확인 → `models/brand_image.py` → GREEN (3 passed)
- [x] **1.2.2** `tests/test_models/test_product.py` → RED → `models/product.py` → GREEN (2 passed)
- [x] **1.2.3** `tests/test_models/test_generated_upload.py` → RED → `models/generated_upload.py` + Product.uploads relationship + cascade → GREEN (4 passed)
- [x] **1.2.4** `models/__init__.py` 에 신규 모델 export (`from models import BrandImage, Product, GeneratedUpload, ...`)
- [x] **1.2.5** `models/history.py` 상단에 legacy 주석 추가
- [x] **1.2.6** `config/database.py init_db()` 를 `import models` 로 단순화 (모든 모델 자동 등록)
- [x] **1.2.7** SQLite 스키마 검증 — 임시 DB 에 brand_images / products / generated_uploads 모두 정상 생성됨 (FK + 인덱스 포함)

**서비스 (RED → GREEN):**
- [x] **1.2.8** `tests/test_services/test_brand_image_service.py` → RED → `services/brand_image_service.py` → GREEN (6 passed)
- [x] **1.2.9** `tests/test_services/test_product_service.py` → RED → `services/product_service.py` → GREEN (6 passed)
- [x] **1.2.10** `tests/test_services/test_upload_service.py` → RED → `services/upload_service.py` → GREEN (5 passed)

**기타:**
- [x] **1.2.11** `S-1` `DB_DIR` 절대경로화 — `Path(__file__).resolve().parent.parent / "data"`
- [x] **종료 검증** 전체 회귀 26 passed + `python -c "import app"` 정상
- [ ] **1.2.12** 커밋: `refactor(Step 1.2): ORM 모델 3종 + CRUD 서비스 + pytest 인프라`

### Step 1.3 — 서비스 레이어 정합 ✅ (잔여 작업)

> 1.3.1 ~ 1.3.3 은 Step 1.1 안에서 처리됨 (커밋 c69586a).

- [x] **1.3.1** ~~`services/image_service.py` 분기 제거 → `backends/registry.py` 호출~~ (Step 1.1 처리)
- [x] **1.3.2** ~~`services/text_service.py` 동일 패턴 정리~~ (Step 1.1 처리)
- [x] **1.3.3** ~~`I-3` text_service 내부 `import re` 파일 상단으로 이동~~ (openai_gpt 작성하면서 자동 처리)
- [x] **1.3.4** `I-1` `TEXT_MODEL` 기본값 `gpt-5-mini` → `gpt-4o-mini` (chat completions 동작 보장)
- [x] **1.3.5** `I-2` `services/caption_service.py` Mock 모드 분기 추가 **(TDD: RED 확인 → GREEN 2 passed)**
- [x] **1.3.6** `I-4` `services/image_service.py` bare except 는 Step 1.1 에서 처리됨. 폰트 경로를 `Settings.STORY_FONT_PATHS` (콜론 구분) 로 분리 + Linux 폰트 fallback 체인 + `_load_story_font()` 메서드 추출
- [x] **1.3.7** `C-1` `services/instagram_service.py` FreeImage API 키 하드코딩 → `Settings.FREEIMAGE_API_KEY` (공용 키는 기본값으로 폴백)
- [x] **1.3.8** `C-3` `services/instagram_service.py` requests → httpx 통일. 추가로 예외 경로의 `target_str` unbound 버그 수정
- [x] **1.3.9** `services/history_service.py` 상단에 LEGACY 주석 추가 (Phase 2 종료 시 제거 예정)
- [x] **1.3.10** 전체 회귀 — pytest 28 passed + `python -c "import app"` 정상
- [ ] **1.3.11** 커밋: `refactor(Step 1.3): 코드 리뷰 잔존 이슈 처리 + caption/history 정리`

### Step 1.4 — UI 구조 정렬 (입력 폼 1차) ✅

- [x] **1.4.1** `utils/goal_categories.py` 신규 — `GOAL_CATEGORIES` tuple + `is_valid_category()` **(TDD: 5 passed)**
- [x] **1.4.2** `app.py` 광고 목적 `st.selectbox` → `st.pills` 칩 6종 + 자유 텍스트 입력란
- [x] **1.4.3** 카테고리 6종 상수는 `utils/goal_categories.py` 에서 단일 소스로 관리
- [x] **1.4.4** `S-3` `TONE_DISPLAY_MAP` + `STYLE_DISPLAY_MAP` → `TONE_STYLE_DISPLAY_MAP` 단일 통합
- [x] **1.4.5** `C-2` `run_async()` 를 `utils/async_runner.py` 로 추출 + 실행 중 루프 시 별도 스레드에서 실행 **(TDD: 2 passed)**
- [x] **1.4.6** `S-2` 인스타 진행률 `min(idx, 1.0)` 클램핑 (피드 + 스토리 양쪽)
- [x] **1.4.7** 신상품 토글 `st.toggle(..., disabled=True)` placeholder 추가 (Phase 2 Step 2.3 에서 활성화)
- [x] **1.4.8** `python -c "import app"` 정상 + pytest 35 passed
- [ ] **1.4.9** 커밋: `refactor(Step 1.4): 광고 목적 칩 UI + 입력 폼 구조 정렬 + 코드 리뷰 잔존 이슈 처리`

### Phase 1 종료 검증

- [x] **P1-1** `services/` 안에서 `from models.sd15 import` 같은 직접 백엔드 import 없음 (grep 검증)
- [x] **P1-2** ORM 신규 모델 3종이 DB 에 실제 생성됨 (Step 1.2.7 임시 DB 스키마 검증)
- [x] **P1-3** 광고 목적 UI 가 `st.pills` 칩 6종 + 자유 텍스트로 동작 (1.4.5)
- [x] **P1-4** 코드 리뷰 잔존 이슈 모두 닫힘:
  - Critical: C-1 (FreeImage 키 .env), C-2 (run_async 버그), C-3 (requests→httpx)
  - Important: I-1 (TEXT_MODEL 기본값), I-2 (CaptionService Mock), I-3 (text_service import 정리), I-4 (폰트 경로 Settings)
  - Suggestion: S-1 (DB_DIR 절대경로), S-2 (진행률 클램핑), S-3 (DISPLAY_MAP 통합)
  - I-5 (Settings `@lru_cache` 캐싱)은 보류 — 기능 영향 없음, Phase 2 이후 검토
- [x] **P1-5** 기존 광고 생성 흐름이 기능 변경 없이 동작 (`python -c "import app"` OK, 35 passed)
- [ ] **P1-6** Phase 1 회고: 의도와 결과 차이 메모 (Step 1.4 커밋 시 compass/plan.md 에 추가)

---

## Phase 2 — MVP 완성

### Step 2.1 — 온보딩 화면 + 자동 파이프라인

- [ ] **2.1.1** `browser-use[cli]>=0.12.6` 의존성 추가 (사용자 확인 후)
- [ ] **2.1.2** `backends/insta_capture.py` 신규 — `scripts/insta_screenshot.py` 로직을 모듈화
- [ ] **2.1.3** `services/onboarding_service.py` 신규
- [ ] **2.1.4** GPT Vision 분석 함수 작성 (사용자 자유 텍스트 + 캡처 이미지 → system prompt 정제 텍스트)
- [ ] **2.1.5** `ui/onboarding.py` 신규 — 자유 텍스트 + 인스타 URL 입력 화면
- [ ] **2.1.6** 검수 화면 (타협 모드 — "그대로 OK" 큰 버튼 + 작은 "수정하기")
- [ ] **2.1.7** `app.py` 라우팅 — 진입 시 brand_image 존재 확인 → 온보딩 또는 광고 화면
- [ ] **2.1.8** 신규 사용자 시뮬레이션 검증 (DB 비우고 처음부터)
- [ ] **2.1.9** 커밋: `feat: 온보딩 화면 + GPT Vision 기반 brand_image 자동 생성`

### Step 2.2 — 참조 이미지 갤러리

- [ ] **2.2.1** `ui/reference_gallery.py` 신규 — 썸네일 그리드 + 다중 선택
- [ ] **2.2.2** `services/upload_service.py` 에 갤러리용 조회 메서드 추가 (게시 완료된 항목만)
- [ ] **2.2.3** `app.py` 광고 생성 폼에 갤러리 통합
- [ ] **2.2.4** `schemas/image_schema.py` 의 `ImageGenerationRequest` 에 `reference_image_paths: list[str]` 추가
- [ ] **2.2.5** 백엔드들이 다중 참조 이미지를 처리하도록 확장 (지원 안 하면 첫 1장만)
- [ ] **2.2.6** 시각 검증: 갤러리 2장 선택 → 광고 생성 → 결과 확인
- [ ] **2.2.7** 커밋: `feat: 참조 이미지 갤러리 + 다중 선택`

### Step 2.3 — 신상품 토글 + 상품 드롭다운

- [ ] **2.3.1** 상품명 입력란 → 드롭다운 (`product` 테이블 조회)
- [ ] **2.3.2** 신상품 토글의 실제 동작 연결 (raw 이미지 업로드란 조건부 노출)
- [ ] **2.3.3** 폼 검증 — 토글 상태별 필수 필드 체크
- [ ] **2.3.4** 신상품 등록 시 백그라운드 product INSERT
- [ ] **2.3.5** 두 시나리오(신상품/기존 상품) 모두 검증
- [ ] **2.3.6** 커밋: `feat: 신상품 토글 + 기존 상품 드롭다운`

### Step 2.4 — 인스타 게시 후 generated_upload 저장

- [ ] **2.4.1** `services/instagram_service.py` 게시 성공 시 `upload_service.create()` 호출
- [ ] **2.4.2** `instagram_post_id`, `posted_at`, `caption`, `image_path` 메타데이터 수집
- [ ] **2.4.3** 게시 실패 시 INSERT 안 함 + 사용자 알림
- [ ] **2.4.4** 게시 1회 후 다음 광고 생성 시 갤러리에 노출되는지 확인
- [ ] **2.4.5** 커밋: `feat: 인스타 게시 성공 시 generated_upload 자동 저장`

### Step 2.5 — 사용자 대기 시간 최소화

- [ ] **2.5.1** `data/staging/` 디렉토리 + .gitignore 추가
- [ ] **2.5.2** 업로드 파일 즉시 staging 저장 로직
- [ ] **2.5.3** 백그라운드 태스크 — 결과 표시 후 DB row 생성 + staging → permanent 이동
- [ ] **2.5.4** 신상품 INSERT, generated_upload INSERT 백그라운드화
- [ ] **2.5.5** 광고 생성 클릭 → 결과 표시까지 시간 측정 (이전 대비 단축 확인)
- [ ] **2.5.6** 커밋: `feat: 백그라운드 DB 쓰기로 사용자 대기 시간 최소화`

### Phase 2 종료 검증

- [ ] **P2-1** 신규 사용자 → 온보딩 → 광고 생성 → 인스타 게시까지 end-to-end 동작
- [ ] **P2-2** 참조 이미지 풀 자동 편입 동작
- [ ] **P2-3** legacy 제거 — `models/history.py`, `services/history_service.py`, `crawl_and_analyze/image_crawler.py`
- [ ] **P2-4** `instaloader` 의존성 제거
- [ ] **P2-5** README.md 갱신 (디렉토리 구조, 의존성)
- [ ] **P2-6** Phase 2 회고

---

## 메타 작업

- [ ] **M-1** Phase 1 시작 전 사용자 검수 (이 문서 + plan.md + context.md)
- [ ] **M-2** Phase 1 종료 후 사용자 검수
- [ ] **M-3** Phase 2 시작 전 사용자 검수
- [ ] **M-4** Phase 2 종료 후 사용자 검수 + design.md 정합성 확인
- [ ] **M-5** PRD.md / architecture.md 와 design.md 정합성 작업 (선택, 후순위)
