# Checklist

> **작성일:** 2026-04-08
> **베이스:** [`plan.md`](plan.md)
> 작업 단위 = 한 줄. 끝내는 즉시 체크. 대부분 1커밋 = 1체크.

---

## Phase 1 — 리팩터링

### Step 1.1 — `backends/` 신설

- [ ] **1.1.1** `backends/__init__.py` 생성
- [ ] **1.1.2** `backends/image_base.py` — `ImageBackend` 프로토콜 작성
- [ ] **1.1.3** `backends/text_base.py` — `TextBackend` 프로토콜 작성
- [ ] **1.1.4** `models/sd15.py` → `backends/hf_sd15.py` 이동 + 인터페이스 준수 확인
- [ ] **1.1.5** `models/ip_adapter.py` → `backends/hf_ip_adapter.py` 이동
- [ ] **1.1.6** `models/img2img.py` → `backends/hf_img2img.py` 이동
- [ ] **1.1.7** `models/hybrid.py` → `backends/hf_hybrid.py` 이동
- [ ] **1.1.8** `models/local_backend.py` 삭제 (역할이 image_base로 흡수됨)
- [ ] **1.1.9** `backends/openai_gpt.py` 신규 (text_service의 GPT 호출 로직 이동)
- [ ] **1.1.10** `backends/remote_worker.py` 신규 (image_service의 remote 분기 이동)
- [ ] **1.1.11** `backends/mock_image.py` / `backends/mock_text.py` 신규
- [ ] **1.1.12** `backends/registry.py` — 환경 변수 기반 백엔드 선택 팩토리
- [ ] **1.1.13** import 경로 일괄 수정 (services, app.py, worker_api.py)
- [ ] **1.1.14** Streamlit 앱 정상 기동 검증
- [ ] **1.1.15** 커밋: `refactor: backends/ 디렉토리 신설 및 백엔드 분리`

### Step 1.2 — ORM 재설계

- [ ] **1.2.1** `models/brand_image.py` — BrandImage 모델 작성
- [ ] **1.2.2** `models/product.py` — Product 모델 작성
- [ ] **1.2.3** `models/generated_upload.py` — GeneratedUpload 모델 작성 + Product 관계
- [ ] **1.2.4** `models/__init__.py` 에 신규 모델 export
- [ ] **1.2.5** `models/history.py` 상단에 legacy 주석 추가
- [ ] **1.2.6** DB 초기화 코드 (`config/database.py`) 가 새 테이블 생성하는지 확인
- [ ] **1.2.7** SQLite 스키마 검증 (`sqlite3 data/history.db ".schema brand_image product generated_upload"`)
- [ ] **1.2.8** `services/brand_image_service.py` 신규 (CRUD)
- [ ] **1.2.9** `services/product_service.py` 신규 (CRUD)
- [ ] **1.2.10** `services/upload_service.py` 신규 (CRUD)
- [ ] **1.2.11** `S-1` `DB_DIR` 절대경로화 (`config/database.py`)
- [ ] **1.2.12** 커밋: `refactor: ORM 모델 3종 추가 (brand_image, product, generated_upload)`

### Step 1.3 — 서비스 레이어 정합

- [ ] **1.3.1** `services/image_service.py` 분기 제거 → `backends/registry.py` 호출
- [ ] **1.3.2** `services/text_service.py` 동일 패턴 정리
- [ ] **1.3.3** `I-3` text_service 내부 `import re` 파일 상단으로 이동
- [ ] **1.3.4** `I-1` `TEXT_MODEL` 기본값을 유효 모델명으로 수정
- [ ] **1.3.5** `I-2` `services/caption_service.py` Mock 모드 분기 추가
- [ ] **1.3.6** `I-4` `services/image_service.py` `compose_story_image()` bare except → `Exception`, 폰트 경로 Settings 분리
- [ ] **1.3.7** `C-1` `services/instagram_service.py` FreeImage API 키 → `.env` + Settings
- [ ] **1.3.8** `C-3` `services/instagram_service.py` requests → httpx 통일 (또는 의존성 추가)
- [ ] **1.3.9** `services/history_service.py` 상단에 legacy 주석
- [ ] **1.3.10** Streamlit 앱 정상 기동 + 1회 이미지 생성 시도 (성공/실패 무관, 분기 동작 확인)
- [ ] **1.3.11** 커밋: `refactor: 서비스 레이어를 백엔드 레지스트리 기반으로 정리 + 코드 리뷰 잔존 이슈 처리`

### Step 1.4 — UI 구조 정렬 (입력 폼 1차)

- [ ] **1.4.1** `ui/widgets.py` 또는 별도 파일로 광고 목적 칩 컴포넌트 작성
- [ ] **1.4.2** `app.py` 광고 목적 단일 드롭다운 → 칩 6종 + 자유 텍스트 입력란
- [ ] **1.4.3** 카테고리 6종 상수 정의 (신메뉴 출시 / 주말·시즌 한정 / 할인·이벤트 / 일상·감성 / 영업 안내 / 감사·안부)
- [ ] **1.4.4** `S-3` `TONE_DISPLAY_MAP` / `STYLE_DISPLAY_MAP` 통합
- [ ] **1.4.5** `C-2` `app.py` `run_async()` else 분기 버그 수정
- [ ] **1.4.6** `S-2` 인스타 진행률 `min(idx, 1.0)` 클램핑
- [ ] **1.4.7** **신상품 토글 placeholder만** 추가 (실제 동작 X)
- [ ] **1.4.8** Streamlit 앱 정상 기동 + 폼 렌더링 시각 확인
- [ ] **1.4.9** 커밋: `refactor: 광고 목적 칩 UI + 입력 폼 구조 정렬`

### Phase 1 종료 검증

- [ ] **P1-1** `services/` 안에서 `from models.sd15 import` 같은 직접 백엔드 import가 없는지 grep
- [ ] **P1-2** ORM 신규 모델 3종이 DB에 실제 생성됨을 확인
- [ ] **P1-3** 광고 목적 UI가 칩으로 동작
- [ ] **P1-4** 코드 리뷰 잔존 이슈 (C-1~C-3, I-1~I-4, S-1~S-3) 모두 닫힘
- [ ] **P1-5** 기존 광고 생성 흐름이 기능 변경 없이 동작
- [ ] **P1-6** Phase 1 회고: 의도와 결과 차이 메모 → context.md 또는 plan.md 갱신

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
