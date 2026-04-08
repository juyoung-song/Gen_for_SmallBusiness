# Plan

> **작성일:** 2026-04-08
> **베이스:** `docs/design.md`
> **이전 버전 폐기:** IP-Adapter 코드 리뷰 작업 계획(2026-04-03)은 본 문서로 대체됨

---

## 0. 작업 원칙

1. **design.md 우선**: 모든 설계 결정의 단일 진실 공급원
2. **1 모듈 = 1 파일**: 새 백엔드/모델은 항상 별도 파일로
3. **공통 인터페이스 우선**: 백엔드는 베이스 프로토콜 구현, 서비스는 인터페이스만 호출
4. **Phase 1 먼저**: 먼저 정리(refactor), 그 다음 추가(add)
5. **외부 서비스/시크릿 추가 작업 전에는 사용자 확인**

## 1. Phase 구조 (큰 그림)

```
Phase 1 — 리팩터링 (구조 정렬)
  └─ Step 1.1: 백엔드 디렉토리 분리
  └─ Step 1.2: ORM 모델 재설계 (brand_image / product / generated_upload)
  └─ Step 1.3: 서비스 레이어 인터페이스 정합
  └─ Step 1.4: 광고 목적/입력 폼 UI 구조 정렬

Phase 2 — MVP 완성 (기능 추가)
  └─ Step 2.1: 온보딩 화면 + 자동 파이프라인
  └─ Step 2.2: 참조 이미지 갤러리
  └─ Step 2.3: 신상품 토글 + 상품 드롭다운
  └─ Step 2.4: 자동 게시 후 generated_upload 저장 흐름
  └─ Step 2.5: 사용자 대기 시간 최소화 (백그라운드 DB 쓰기)
```

각 Step은 **독립 커밋 단위**로 진행한다. Step 종료 시점마다 빌드/실행 검증.

---

## Phase 1 — 리팩터링

### Step 1.1: `backends/` 디렉토리 신설 및 백엔드 이동

**목표**: 이미지/텍스트 생성 백엔드를 ORM 모델과 분리.

**작업**:
1. 신규 디렉토리 `backends/` 생성
2. 베이스 인터페이스 작성
   - `backends/image_base.py` — `ImageBackend` 프로토콜 (`generate(request)`, `is_available()`)
   - `backends/text_base.py` — `TextBackend` 프로토콜 (`generate_copy(request)`, `is_available()`)
3. 기존 `models/` 의 백엔드 파일 이동 + 이름 변경
   - `models/sd15.py` → `backends/hf_sd15.py`
   - `models/ip_adapter.py` → `backends/hf_ip_adapter.py`
   - `models/img2img.py` → `backends/hf_img2img.py`
   - `models/hybrid.py` → `backends/hf_hybrid.py`
   - `models/local_backend.py` → 삭제 (역할이 `backends/image_base.py` 로 흡수됨)
4. 새 백엔드 파일 신설
   - `backends/openai_gpt.py` — TextBackend 구현 (기존 `services/text_service.py` 의 GPT 호출 로직 이동)
   - `backends/remote_worker.py` — 원격 워커 호출 (기존 `services/image_service.py` 의 remote 분기 이동)
   - `backends/mock_image.py` / `backends/mock_text.py` — Mock 응답 (기존 `_mock_response()` 이동)
5. import 경로 일괄 수정 (`models.sd15` → `backends.hf_sd15` 등)
6. `services/` 는 백엔드를 직접 import하지 않고 **팩토리/레지스트리** 통해 선택
   - `backends/__init__.py` 또는 `backends/registry.py` 에서 환경 변수 기반 선택

**검증**: `python -c "import backends; from backends.hf_sd15 import HFSD15Backend; ..."` 성공, 기존 Streamlit 앱 정상 기동

**커밋 메시지(안)**: `refactor: backends/ 디렉토리 신설 및 이미지/텍스트 백엔드 분리`

---

### Step 1.2: ORM 재설계 — `brand_image` / `product` / `generated_upload`

**목표**: design.md §2 데이터 모델을 ORM으로 구현.

**작업**:
1. `models/brand_image.py` 신규
   - 필드: `id (UUID, PK)`, `user_id (str, default='default')`, `content (Text, system prompt)`, `source_freetext (Text)`, `source_reference_url (Text)`, `source_screenshots (JSON)`, `created_at`
2. `models/product.py` 신규
   - 필드: `id (UUID, PK)`, `name (str, indexed)`, `description (Text)`, `raw_image_path (str)`, `created_at`
3. `models/generated_upload.py` 신규
   - 필드: `id (UUID, PK)`, `product_id (FK)`, `image_path (str)`, `caption (Text)`, `goal_category (str)`, `goal_freeform (Text)`, `instagram_post_id (str, nullable)`, `posted_at (datetime, nullable)`, `created_at`
   - 관계: `product = relationship("Product", back_populates="uploads")`
4. `models/history.py` — **legacy 표시**, 신규 코드는 사용 금지 주석 추가. Phase 2 종료 시 제거.
5. DB 마이그레이션
   - 신규 테이블 생성 (Alembic 도입은 Phase 2에서 검토. MVP는 `Base.metadata.create_all()` 로 충분)
   - 기존 `history` 테이블은 그대로 두되 새 코드는 사용 금지

**검증**: SQLite DB에 새 테이블 3종 생성 확인 (`sqlite3 data/history.db ".schema brand_image"` 등)

**커밋 메시지(안)**: `refactor: brand_image / product / generated_upload ORM 모델 추가`

---

### Step 1.3: 서비스 레이어 인터페이스 정합

**목표**: 서비스가 백엔드를 직접 알지 않고 인터페이스만 사용하도록 정리.

**작업**:
1. `services/image_service.py` 정리
   - 분기 로직 제거 (`USE_MOCK`, `USE_LOCAL_MODEL`, `IMAGE_BACKEND` 분기) → `backends/registry.py` 호출로 대체
   - `generate_ad_image(request)` 단순화: 백엔드 선택 → 호출 → 응답
2. `services/text_service.py` 정리
   - 동일한 패턴으로 정리
3. `services/instagram_service.py`
   - 본래 잘 정돈되어 있으므로 시그니처 변경 없음
   - 단, 게시 성공 시 `generated_upload` 레코드 저장 콜백 추가 (Phase 2 Step 2.4와 연동)
4. `services/caption_service.py`
   - Mock 모드 분기 추가 (이전 리뷰의 I-2 항목)
5. `services/history_service.py`
   - **legacy 표시** + 신규 서비스로 분리 (`services/product_service.py`, `services/upload_service.py`, `services/brand_image_service.py`)
   - 새 서비스들은 Step 1.2의 ORM 모델 CRUD

**검증**: `streamlit run app.py` 시 정상 동작 (기능 변경 없이 내부 구조만 정리됨)

**커밋 메시지(안)**: `refactor: 서비스 레이어를 백엔드 레지스트리 기반으로 단순화`

---

### Step 1.4: UI 구조 정렬 (입력 폼 1차)

**목표**: 입력 폼의 구조를 design.md §4.1 에 맞게 정렬. 기능 추가는 Phase 2에서.

**작업**:
1. 광고 목적 UI: 단일 드롭다운 → **칩 6종 + 자유 텍스트**
   - 카테고리 6종: 신메뉴 출시 / 주말·시즌 한정 / 할인·이벤트 / 일상·감성 / 영업 안내 / 감사·안부
   - 칩 UI: `st.pills()` 또는 `st.radio(horizontal=True)` 활용
2. 톤/스타일 라디오 정리
   - 텍스트 톤 / 이미지 스타일 중복 제거 (이전 리뷰 S-3)
3. **신상품 토글 placeholder**만 추가 (실제 동작은 Step 2.3에서)
4. **참조 이미지 입력은 이전 그대로** (갤러리 변경은 Step 2.2에서)
5. **상품명은 이전 그대로** (드롭다운 변경은 Step 2.3에서)

**검증**: 폼 렌더링 정상, 값이 기존 서비스 호출에 그대로 전달됨

**커밋 메시지(안)**: `refactor: 광고 목적을 칩 UI + 자유 텍스트로 변경`

---

## Phase 2 — MVP 완성

### Step 2.1: 온보딩 화면 + 자동 파이프라인

**목표**: design.md §3 온보딩 플로우 구현.

**작업**:
1. UI 라우팅 도입
   - `app.py` 진입 시 brand_image 존재 여부 확인
   - 없으면 → 온보딩 화면, 있으면 → 광고 생성 화면
2. 온보딩 화면 (`ui/onboarding.py` 신규)
   - 입력: 자유 텍스트 + 인스타 프로필 URL 1개
   - "분석 시작" 버튼 → `services/onboarding_service.py` 호출
3. `services/onboarding_service.py` 신규
   - **단계 1**: `scripts/insta_screenshot.py` 의 로직을 모듈로 추출 → `backends/insta_capture.py` (browser-use CLI subprocess 호출)
     - 캡처 1~2장
     - **(주의)** browser-use CLI 의존성 추가 필요 (`pyproject.toml`)
   - **단계 2**: GPT Vision 분석 → 사용자 자유 텍스트 + 캡처 이미지 → system prompt 정제 텍스트
     - `crawl_and_analyze/image_analyzer.py` 의 로직을 참고하되 `services/onboarding_service.py` 안에 통합
   - **단계 3**: 검수 화면 (타협 모드 — "그대로 OK" 큰 버튼 + 작은 "수정하기")
   - **단계 4**: 확정 시 `BrandImage` 레코드 저장 (이후 불변)
4. 의존성 추가
   - `browser-use[cli]>=0.12.6` (단, 사용자 확인 후)

**검증**: 신규 사용자 시뮬레이션 (DB 비우고 `streamlit run app.py`) → 온보딩 화면 → brand_image.txt 생성 → 광고 화면으로 진입

**커밋 메시지(안)**: `feat: 온보딩 화면 + GPT Vision 기반 brand_image 자동 생성`

---

### Step 2.2: 참조 이미지 갤러리

**목표**: 매 광고 생성 시 기존 generated_upload 풀에서 다중 선택 가능.

**작업**:
1. `ui/reference_gallery.py` 신규
   - `generated_upload` 테이블에서 인스타 게시 완료 항목 모두 조회
   - 썸네일 그리드로 렌더 (Streamlit `st.image` + columns)
   - 다중 선택 (체크박스 또는 클릭 토글)
   - 선택된 ID 리스트를 폼에 반영
2. 광고 생성 폼에 갤러리 통합
   - "참조 이미지 (옵션)" 섹션 → 갤러리 호출
   - 선택된 이미지들이 컨텍스트 조립에 포함됨 (`request.reference_image_ids`)
3. 백엔드 측 수정
   - `ImageGenerationRequest` 에 `reference_image_paths: list[str]` 추가
   - 백엔드는 다중 참조 이미지를 지원하는 경우 모두 활용 (지원 안 하면 첫 1장만)

**검증**: 갤러리에서 2장 선택 → 광고 생성 → 결과가 두 톤이 섞여있는 듯한지 시각 확인

**커밋 메시지(안)**: `feat: 참조 이미지 갤러리 + 다중 선택 지원`

---

### Step 2.3: 신상품 토글 + 상품 드롭다운

**목표**: design.md §4.1 의 상품 입력 UX 완성.

**작업**:
1. 상품명 드롭다운
   - `product` 테이블에서 모든 상품 조회 → `st.selectbox` (또는 `st.combobox`)
   - 검색 가능
2. 신상품 토글
   - `st.toggle("신상품 등록")` 추가
   - **ON**: raw 이미지 업로드란 노출 + 필수화. 상품명/설명도 새로 입력
   - **OFF**: 드롭다운에서 상품 선택 → DB에서 raw_image 자동 로드
3. 폼 검증
   - 토글 OFF + 드롭다운 미선택 → 에러
   - 토글 ON + raw 이미지 미업로드 → 에러
4. 신상품인 경우 광고 생성 후 백그라운드로 `product` 테이블에 INSERT

**검증**: 두 시나리오 모두 정상 동작 + 신상품 등록 후 다음 광고 생성 시 드롭다운에 노출됨

**커밋 메시지(안)**: `feat: 신상품 토글 + 기존 상품 드롭다운`

---

### Step 2.4: 자동 게시 후 `generated_upload` 저장 흐름

**목표**: 인스타 게시 성공 시 generated_upload 테이블에 INSERT → 다음 생성의 참조 이미지 풀로 자동 편입.

**작업**:
1. `services/instagram_service.py` 의 게시 성공 콜백
   - 성공 시 `services/upload_service.py` 호출 → `GeneratedUpload` INSERT
   - 게시 실패 시 INSERT 안 함 (참조 풀에 미등록)
2. 광고 생성 결과에서 인스타 메타데이터 수집
   - `instagram_post_id`, `posted_at`, `caption`, `image_path` 저장
3. 게시 실패 시 백그라운드 재시도 정책 정의 (최대 3회, 지수 백오프)

**검증**: 게시 1회 성공 → DB의 `generated_upload` 에 1행 추가 → 다음 광고 생성의 참조 갤러리에 노출됨

**커밋 메시지(안)**: `feat: 인스타 게시 성공 시 generated_upload 자동 저장 + 참조 풀 편입`

---

### Step 2.5: 사용자 대기 시간 최소화 (백그라운드 DB 쓰기)

**목표**: design.md §4.4 의 하이브리드 정책 구현.

**작업**:
1. 업로드 파일은 받자마자 `data/staging/{uuid}.jpg` 에 저장 (동기, ~50ms)
2. 백엔드 호출 시작 (메인 스레드, 사용자 대기)
3. 결과 표시 후 → 백그라운드 태스크로:
   - DB row 생성 (product / generated_upload)
   - staging → permanent 파일 이동
   - 신상품이면 product 테이블 INSERT
   - 인스타 업로드 성공 시 generated_upload INSERT
4. 백그라운드 태스크는 `asyncio.create_task` 또는 `concurrent.futures` 활용
5. 실패 시 사용자에게 작은 알림 ("저장 중 오류 — 재시도 중")

**검증**: 광고 생성 → 결과 표시까지 소요 시간 측정. DB I/O가 메인 경로에서 빠진 것 확인.

**커밋 메시지(안)**: `feat: 사용자 대기 시간 최소화 — 백그라운드 DB 쓰기 분리`

---

## 3. Phase 외 작업 (병렬 가능)

### legacy 정리
- Phase 2 종료 시 `models/history.py`, `services/history_service.py` 제거
- `crawl_and_analyze/image_crawler.py` 제거 (이미 `feature/won/insta-snapshot` 에서 처리됨, 본 브랜치에 cherry-pick)

### 의존성 정리
- `browser-use[cli]` 추가 (Step 2.1)
- `instaloader` 제거 (legacy 정리 시)
- `requirements.txt` ↔ `pyproject.toml` 동기화

### 과거 이슈 처리 (compass 이전 버전 잔존)
이전 코드 리뷰의 미해결 이슈들 중 본 리팩터링과 무관하거나 작은 것들. Step 1~2 진행 중 발견되면 그 자리에서 처리하거나, 끝난 후 별도 PR.

| 이슈 | 처리 시점 |
|------|---------|
| C-1 FreeImage API 키 .env로 이동 | Phase 1 Step 1.3 (instagram_service 손볼 때) |
| C-2 `run_async()` else 분기 버그 | Phase 1 Step 1.4 (app.py 손볼 때) |
| C-3 `requests` 의존성 | Phase 1 Step 1.3 (httpx 통일) |
| I-1 `TEXT_MODEL` 기본값 | Phase 1 Step 1.3 |
| I-2 CaptionService Mock 분기 | Phase 1 Step 1.3 |
| I-3 `_parse_response` 내부 import | Phase 1 Step 1.3 |
| I-4 bare except + 폰트 경로 | Phase 1 Step 1.3 |
| I-5 `@lru_cache` Settings 캐싱 | 후순위 |
| S-1 DB_DIR 절대경로화 | Phase 1 Step 1.2 |
| S-2 진행률 클램핑 | Phase 1 Step 1.4 |
| S-3 Display map 중복 | Phase 1 Step 1.4 |

---

## 4. 리스크 / 확인 필요한 것

| 리스크 | 영향 | 대응 |
|--------|------|------|
| `nano banana` 실제 호출 인터페이스 미정 | Step 2.1 이후 광고 생성 실제 동작 검증 불가 | 우선 mock_image 백엔드로 진행, 인터페이스 확정 시 별도 PR |
| GPT Vision 분석 결과 품질 (brand_image.txt) | 잘못 작성되면 모든 광고가 잘못된 톤 | 검수 단계 필수, 사용자 수정 가능 |
| `browser-use` CLI 의존성 추가 | 패키지 무거움 (Playwright 포함) | 사용자 확인 후 진행 |
| Alembic 미도입 | 스키마 변경 시 수동 마이그레이션 | MVP는 SQLite create_all() 로 충분, v2에서 도입 |
| 다른 브랜치 작업물 머지 충돌 | 리팩터링 후 cherry-pick 시 충돌 가능 | 각 Step 종료 시 dev 변동 모니터링 |

## 5. Phase 종료 기준

**Phase 1 완료 조건**:
- [ ] `backends/` 디렉토리 신설 + 모든 백엔드 이동 완료
- [ ] ORM 3종 (brand_image, product, generated_upload) 추가
- [ ] 서비스 레이어가 백엔드 직접 import 안 함 (인터페이스만 사용)
- [ ] 기존 Streamlit 앱이 기능 변경 없이 정상 동작
- [ ] 광고 목적 UI = 칩 + 자유 텍스트
- [ ] 코드 리뷰 잔존 이슈 (C-1~C-3, I-1~I-4, S-1~S-3) 처리

**Phase 2 완료 조건**:
- [ ] 신규 사용자 시뮬레이션이 온보딩 → 광고 생성 → 인스타 게시까지 끊김 없이 동작
- [ ] 참조 이미지 갤러리에서 다중 선택 가능
- [ ] 신상품 토글 + 상품 드롭다운 정상 동작
- [ ] 인스타 게시 성공 시 generated_upload 자동 저장
- [ ] DB I/O가 메인 경로에서 빠짐 (백그라운드)
- [ ] legacy 코드 (`history.py`, `crawl_and_analyze/image_crawler.py`) 제거
