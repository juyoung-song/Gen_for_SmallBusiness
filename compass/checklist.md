# Checklist

> **작성일:** 2026-04-08
> **마지막 갱신:** 2026-04-08 (Phase 2 완료)
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

### Step 2.1 — 온보딩 화면 + 자동 파이프라인 ✅

- [x] **2.1.1** `browser-use[cli]>=0.12.6` 의존성 추가
- [x] **2.1.2** `backends/insta_capture.py` 신규 — browser-use CLI subprocess 래퍼 + `parse_close_button_index()` 순수 함수 **(TDD: 4 passed)**
- [x] **2.1.3** `services/onboarding_service.py` 신규 — `OnboardingService`, `BrandImageDraft`, `GPTVisionAnalyzer`, `build_vision_analysis_prompt()` **(TDD: 6 passed, 외부 의존성은 주입형 Protocol 로 테스트 가능)**
- [x] **2.1.4** GPT Vision 분석 — `GPTVisionAnalyzer.analyze()` 가 base64 인코딩된 이미지 + system prompt 로 호출
- [x] **2.1.5** `ui/onboarding.py` 신규 — 2단계 화면 (입력 → 검수)
- [x] **2.1.6** 검수 화면 타협 모드 — "이대로 확정" 큰 버튼 (col 3) + "수정하기" 작은 버튼 (col 1) + "처음부터 다시"
- [x] **2.1.7** `app.py` 라우팅 — 진입 시 `BrandImageService.exists_for_user` 로 존재 확인, 없으면 `render_onboarding_screen` + `st.stop()`
- [ ] **2.1.8** 신규 사용자 시뮬레이션 검증 — 실제 Streamlit 기동 + 엔드투엔드는 수동 검증 필요
- [ ] **2.1.9** 커밋: `feat(Step 2.1): 온보딩 화면 + GPT Vision 기반 brand_image 자동 생성`

### Step 2.2 — 참조 이미지 갤러리 ✅

- [x] **2.2.1** `schemas/image_schema.py` `ImageGenerationRequest.reference_image_paths: list[str]` 추가 **(TDD: 3 passed)**
- [x] **2.2.2** `services/upload_service.py list_published()` 는 Step 1.2 에서 이미 구현됨 (인스타 게시 완료만 조회)
- [x] **2.2.3** `ui/reference_gallery.py` 신규 — 썸네일 3-컬럼 그리드 + 체크박스 다중 선택, 최근 24장 제한
- [x] **2.2.4** `app.py` — 광고 목적 섹션 아래 expander 로 갤러리 통합, 선택 경로를 `_run_*_generation` 에 전달
- [x] **2.2.5** 백엔드 확장 — `ImageService._resolve_reference_image_data()` 순수 메서드 추가. raw 이미지 있으면 그대로, 없으면 참조 첫 장을 `image_data` 로 주입. 백엔드 개별 수정 없음 **(TDD: 4 passed)**
- [x] **2.2.6** 전체 회귀 52 passed + `python -c "import app"` 정상. 실제 UI 동작은 수동 검증 필요
- [ ] **2.2.7** 커밋: `feat(Step 2.2): 참조 이미지 갤러리 + 다중 선택`

### Step 2.3 — 신상품 토글 + 상품 드롭다운 ✅

- [x] **2.3.0** `utils/staging_storage.py` 신규 — `save_to_staging(bytes, extension) → Path` 순수 유틸, `STAGING_DIR` 기반 **(TDD: 4 passed)**
- [x] **2.3.1** 상품명 입력란 → 토글 OFF 시 드롭다운 (`ProductService.list_all()` 조회)
- [x] **2.3.2** 신상품 토글 실제 동작 연결 — 토글 ON 시 상품명/설명/raw 이미지 업로드 폼, OFF 시 드롭다운
- [x] **2.3.3** 폼 검증 — 토글 상태별 필수 필드 체크 (신상품: 이름/설명/이미지, 기존: 드롭다운 선택)
- [x] **2.3.4** 신상품 등록 시 업로드 bytes 즉시 staging 저장 + `ProductService.create()` 로 Product INSERT. 백그라운드화는 Step 2.5
- [x] **2.3.5** 전체 회귀 56 passed + `python -c "import app"` 정상. UI 시나리오는 수동 검증 필요
- [ ] **2.3.6** 커밋: `feat(Step 2.3): 신상품 토글 + 기존 상품 드롭다운`

### Step 2.4 — 인스타 게시 후 generated_upload 저장 ✅

- [x] **2.4.1** `services/instagram_service.py`
  - `last_post_id`, `last_posted_at` 인스턴스 속성 추가
  - Mock 모드: `mock_<uuid>` 형식 가짜 post id 기록
  - Real 모드: Meta `/media_publish` 응답의 `id` 기록
  - **(TDD: 4 passed)** — 초기값 None, mock/real 모두 제너레이터 소진 후 값 채워짐, 연속 호출 시 덮어쓰기
- [x] **2.4.2** 광고 생성 시점에 `st.session_state.current_product_id` + `current_generated_image_path` 보존 (신상품/기존 상품 모두)
- [x] **2.4.3** `_persist_generated_upload()` 헬퍼 — `"DONE"` 수신 시 `UploadService.create()` + `mark_posted()` 순차 호출
  - goal 은 `"카테고리 · 자유텍스트"` 포맷을 역파싱해 goal_category / goal_freeform 분리
  - product_id 또는 image_path 누락 시 저장 스킵 (경고 로그)
- [x] **2.4.4** 게시 실패 시 (제너레이터가 예외로 중단) `_persist_generated_upload` 가 호출되지 않으므로 INSERT 없음
- [x] **2.4.5** 게시 1회 후 다음 광고 생성 시 reference_gallery 에 노출되는지는 `list_published()` 동작으로 보장됨
- [x] **2.4.6** 전체 회귀 60 passed + `python -c "import app"` 정상
- [ ] **2.4.7** 커밋: `feat(Step 2.4): 인스타 게시 성공 시 generated_upload 자동 저장`

### Step 2.5 — legacy 제거 (범위 축소됨) ✅

> **범위 축소 근거:** 원래 계획은 "DB I/O 백그라운드화" 였으나, 실측 기반 병목이
> 아닌 상태에서 복잡도만 올라감. 실질 개선이 되는 **legacy 정리** 로 범위를 축소.
> 백그라운드화는 배포 후 실측 기반으로 별도 진행.

- [x] **2.5.1** 사용처 전수 분석 — `HistoryService` / `HistoryCreate` / `GenerationType` / `History`
- [x] **2.5.2** `_run_text_generation` / `_run_image_generation` / `_run_combined_generation` 에서 `HistoryService().save_history()` 호출 제거
- [x] **2.5.3** 아카이브 탭을 `UploadService.list_published()` + `ProductService.list_all()` 기반으로 재작성 (인스타 게시 완료 항목만 표시)
- [x] **2.5.4** legacy 파일 git rm — `services/history_service.py`, `schemas/history_schema.py`, `models/history.py`
- [x] **2.5.5** `models/__init__.py` 에서 `History` / `GenerationType` re-export 제거
- [x] **2.5.6** `tests/conftest.py` 의 `import models.history` 제거
- [x] **2.5.7** `app.py` 의 legacy import 3개 제거 (`GenerationType`, `HistoryCreate`, `HistoryService`)
- [x] **2.5.8** 전체 회귀 60 passed + `python -c "import app"` 정상 (숫자 변동 없음 — legacy 테스트가 없었음)
- [x] **2.5.9** `compass/context.md` 의 잘 구현된 부분에서 `HistoryService` 언급 갱신
- [ ] **2.5.10** 커밋: `refactor(Step 2.5): legacy HistoryService 제거 + 아카이브 탭 재작성`

### Phase 2 종료 검증 ✅

- [ ] **P2-1** 신규 사용자 → 온보딩 → 광고 생성 → 인스타 게시까지 end-to-end 동작 **(사용자 수동 검증 필요)**
- [x] **P2-2** 참조 이미지 풀 자동 편입 동작 — Step 2.4 의 `mark_posted()` → `list_published()` 경로로 보장됨
- [x] **P2-3** legacy 제거 — `models/history.py`, `services/history_service.py`, `schemas/history_schema.py`, `crawl_and_analyze/image_crawler.py`, `crawl_and_analyze/image_analyzer.py`, `crawl_and_analyze/` 전체
- [x] **P2-4** `instaloader` 의존성 제거 — pyproject.toml / uv.lock / requirements.txt 모두 동기화
- [x] **P2-5** README.md §5 디렉토리 구조 전면 갱신 — backends, models, services, ui, utils, tests, compass, docs 모두 반영
- [x] **P2-6** Phase 2 회고 — compass/plan.md 말미에 기록

---

## 메타 작업

- [ ] **M-1** Phase 1 시작 전 사용자 검수 (이 문서 + plan.md + context.md)
- [ ] **M-2** Phase 1 종료 후 사용자 검수
- [ ] **M-3** Phase 2 시작 전 사용자 검수
- [ ] **M-4** Phase 2 종료 후 사용자 검수 + design.md 정합성 확인
- [ ] **M-5** PRD.md / architecture.md 와 design.md 정합성 작업 (선택, 후순위)

---

## CP17 — mobile_app 백엔드 기능 보존 통합 (2026-04-15)

### Phase 0 — codex/infra 통합 (선결)
- [x] **17.0.1** `git fetch --all` 후 `git merge origin/codex/infra --no-ff` (브랜치: merge/main)
- [x] **17.0.2** `config/settings.py` 충돌 시 둘 다 살리는 방향으로 수동 해결 — 충돌 없이 자동 머지됨
- [x] **17.0.3** `python -m pytest -q` 회귀 통과 (149 passed)

### Phase 1 — RED (TDD 명세 박기)
- [x] **17.1.1** `TestCP17OnboardingAutoLogo::test_complete_onboarding_auto_generates_logo_when_missing` 추가
- [x] **17.1.2** `TestCP17GenerateLogoPathInjection::test_image_request_carries_brand_logo_path` 추가
- [x] **17.1.3** `TestCP17GenerateReferenceAnalysisInjection::test_image_request_carries_composition_prompt` 추가
- [x] **17.1.4** `TestCP17TextRequestKeepsReferenceAnalysisEmpty::test_text_request_reference_analysis_empty_even_with_reference` 추가
- [x] **17.1.5** 4개 모두 RED 확인 (AttributeError: ReferenceAnalyzer/LogoAutoGenerator 없음)

### Phase 2 — GREEN (mobile_app.py 통합)
- [x] **17.2.1** import 추가: `LogoAutoGenerator`, `ReferenceAnalyzer`
- [x] **17.2.2** 상수 신설: `LOGO_FONT_PATH`, `BRAND_ASSETS_DIR`
- [x] **17.2.3** `complete_onboarding` else 블록: 로고 미업로드 시 `LogoAutoGenerator.generate_and_save` 호출
- [x] **17.2.4** `mobile_generate` 에서 `reference_bytes` → `ReferenceAnalyzer.analyze` 호출, `composition_prompt` 추출
- [x] **17.2.5** `ImageGenerationRequest` 에 `reference_analysis=composition_prompt`, `logo_path=brand.logo_path` 주입
- [x] **17.2.6** `TextGenerationRequest` 의 `reference_analysis=""` 정책 유지
- [x] **17.2.7** RED 4개 GREEN 전환 + 전체 회귀 통과 (153 passed)

### Phase 3 — REFACTOR
- [ ] **17.3.1** inline 충분한지 vs `_resolve_reference_analysis` 헬퍼 분리 판단

### 📱 백엔드 동등성 스모크 (uvicorn mobile_app:app)
- [x] **17.S.1** 온보딩(로고 미업로드) → `data/brand_assets/<uuid>.png` 생성 + `brands.logo_path` 채워짐
- [x] **17.S.2** 광고 생성 → 컵에 워드마크 각인 (CP15 동작)
- [x] **17.S.3** 광고 생성 → 다른 프롭 blank (CP16 동작)
- [x] **17.S.4** 광고 생성(참조 이미지 제공) → reference_analysis 주입 자체는 동작. 결과 이미지 구도 반영은 프롬프트 품질 이슈 — 별도 개선 예정

### CP18 — 신상품 사진(product_image) API 주입 (2026-04-15)
- [x] **18.1** `MobileGenerateRequest`에 `product_image: DataUrlFile | None` 추가
- [x] **18.2** `mobile_generate()`에서 `product_image_bytes` 디코딩 → `ImageGenerationRequest.image_data` 주입
- [x] **18.3** `is_new_product = product_image_bytes is not None` 자동 설정
- [x] **18.4** RED→GREEN: `TestCP18ProductImageInjection` (154 passed)

### UI 보충 — codex/infra 선별 이식 (2026-04-15)
- [x] **UI.1** `stitch/3./code.html`: AI Brand Analysis 패널 추가 (분석 결과 표시 + "다음" 버튼 전환)
- [x] **UI.2** `stitch/4._2/code.html`: 신상품 사진 업로드 패널 추가 + 참고 이미지 라벨 개선
- [x] **UI.3** `stitch/shared.js`: `isNewProductGoal()`, `syncProductImageUi()`, `applyAnalysisContent()` 추가
- [ ] **UI.4** Langfuse 브라우저 헤더(`buildTraceHeaders`) — 테스트 미완, 별도 이슈로 분리

### 📱 통합 스모크 최종 결과 (2026-04-15)
- [x] 17.S.1 ✅
- [x] 17.S.2 ✅
- [x] 17.S.3 ✅
- [x] 17.S.4 △ (연결 동작, 구도 품질 개선 필요)
- [x] UI.1 ✅
- [x] UI.2 ✅

---

## CP19 — 신상품 토글 + 기존 상품 선택 UI ✅ (2026-04-15 완료)

### Phase 1 — RED
- [x] **19.1.1** `TestCP19NewProductRequestSchema::test_request_has_is_new_product_field`
- [x] **19.1.2** `TestCP19NewProductValidation::test_new_product_without_image_returns_400`
- [x] **19.1.3** `TestCP19SaveGenerationPersistsProductImage::test_product_image_path_and_is_new_product_persisted`
- [x] **19.1.4** `TestCP19ExistingProductSkipsProductImage::test_existing_product_has_null_product_image_path`
- [x] **19.1.5** `TestCP19ExistingProductsEndpoint::test_lists_products_for_brand`
- [x] **19.1.6** `TestCP19ExistingProductImageLoad::test_existing_product_bytes_injected_into_image_request`

### Phase 2 — GREEN (mobile_app.py)
- [x] **19.2.1** `MobileGenerateRequest.is_new_product` + `existing_product_name` 필드 추가
- [x] **19.2.2** 신상품 + 사진 없음 검증 → 400
- [x] **19.2.3** `_save_generation_outputs()` 파라미터 확장 (`product_image_bytes`, `is_new_product`)
- [x] **19.2.4** 기존 상품 분기: DB `product_image_path` → bytes 로드 → `image_data` 주입
- [x] **19.2.5** `GET /api/mobile/products` 엔드포인트 + `MobileProductGroup` 스키마

### Phase 3 — Stitch UI
- [x] **19.3.1** `stitch/4._2/code.html`: 신상품 토글 + 기존 상품 드롭다운/썸네일
- [x] **19.3.2** `stitch/shared.js`: state + 토글 리스너 + `/products` fetch + 폼 검증
- [x] **19.3.3** 토글 OFF 시 "신제품 출시" goal 버튼 비활성화 + 자동 리셋 (Streamlit 동등, `syncGoalAvailability`)

### 📱 스모크
- [x] **19.S.1** 신상품 ON + 사진 → 생성 성공, DB `is_new_product=1`, `product_image_path=<경로>`
- [x] **19.S.2** 신상품 ON + 사진 없음 → 400 토스트
- [x] **19.S.3** 신상품 OFF + 기존 상품 선택 → 드롭다운 + 썸네일 + 결과 이미지에 과거 상품 반영
- [x] **19.S.4** 신상품 OFF + 미선택 → 에러
- [x] **19.S.5** 회귀: CP17/CP18 기능 유지

---

## CP20 — 인스타 계정 선택 UI (2026-04-15 완료, `merge/insta` 브랜치)

### Phase 1 — RED
- [x] **20.1.1** `TestCP20FetchDefensive::test_missing_data_field_raises`
- [x] **20.1.2** `TestCP20FetchDefensive::test_username_fetch_failure_raises`
- [x] **20.1.3** `TestCP20ListCandidates::test_returns_all_accounts_with_username`
- [x] **20.1.4** `TestCP20CandidatesEndpoint::test_get_candidates_returns_list`
- [x] **20.1.5** `TestCP20SelectAccount::test_post_select_saves_connection`
- [x] **20.1.6** `TestCP20ManualAccount::test_post_manual_saves_connection`

### Phase 2 — GREEN
- [x] **20.2.1** `InstagramAuthService.fetch_instagram_account()` — data 누락 / username 실패 방어 코드 (이미 존재 확인)
- [x] **20.2.2** ~~`MultipleAccountsFound` 예외~~ → `list_candidate_accounts()` 반환값 개수로 분기 (설계 변경)
- [x] **20.2.3** `InstagramAuthService.list_candidate_accounts(token)` 신규 메서드
- [x] **20.2.4** `GET /api/mobile/instagram/candidates` 엔드포인트 (+ `env_account_id` 반환)
- [x] **20.2.5** `POST /api/mobile/instagram/select-account` 엔드포인트
- [x] **20.2.6** `POST /api/mobile/instagram/manual-account` 엔드포인트
- [x] **20.2.7** 콜백: 1개→즉시저장, 2+→`select_required`, 0개→`manual_required`

### Phase 3 — Stitch UI
- [x] **20.3.1** `stitch/settings.html` — `#settings-ig-select-panel` (드롭다운 + 연결 버튼)
- [x] **20.3.2** `stitch/settings.html` — `#settings-ig-manual-panel` (수동 입력 폼)
- [x] **20.3.3** `stitch/shared.js` — `select_required`/`manual_required` 분기 (settings)
- [x] **20.3.4** `shared.js` — `/candidates` fetch + 드롭다운 렌더 + `/select-account` 호출 (settings + 온보딩)
- [x] **20.3.5** `shared.js` — 수동 입력 `/manual-account` 호출 + `env_account_id` 기본값 주입 (settings + 온보딩)
- [x] **20.3.6** `stitch/onboarding-instagram.html` — `#onboarding-ig-select-panel`, `#onboarding-ig-manual-panel` 추가 (온보딩 동등 기능)

### 📱 스모크
- [x] **20.S.1** 페이지 없음 → `manual_required` → 수동 ID 입력 → 연결 완료 (VM 실사용 확인)
- [x] **20.S.2** 페이지 2+ + 각 IG → `select_required` → 선택 UI → 완료 (실계정 환경 미확보, 코드 경로 테스트로 갈음)
- [x] **20.S.3** 페이지 1개 + IG 1개 → 자동 완료 (실계정 환경 미확보, 코드 경로 테스트로 갈음)
- [ ] **20.S.4** 잘못된 ID 수동 입력 → 에러 토스트
- [x] **20.S.5** 회귀: CP19/CP17/CP18 기능 유지 (pytest 34 passed)
