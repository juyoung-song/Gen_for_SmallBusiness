# 데이터 스키마 — 확정안

브랜치: `refactor/flow`. 본 문서는 신규 스키마의 **단일 진실 원천**이며, 구현(`models/`)은 이 문서를 따른다.

관련 문서:
- 개선안/미래 후보: [schema_future.md](schema_future.md)
- 온보딩/생성 플로우: [onboarding.md](onboarding.md), [generation.md](generation.md)

---

## 1. 설계 원칙

| # | 원칙 | 스키마가 방어하는 방식 |
|---|------|----------------------|
| 1 | 브랜드 = 이름/로고/컬러 | `brands` 에 집약 |
| 2 | 스타일(브랜드 톤) ≠ 구도(카메라 앵글) | **다른 테이블, 다른 컬럼**: `brands.style_prompt` vs `reference_images.composition_prompt` |
| 3 | 참조 이미지는 구도 전용, 톤 바꾸는 용도 아님 | `reference_images` 에 `color/mood/tone` 컬럼 **의도적 누락** |
| 4 | 온보딩 후 브랜드 수정 불가 | `brands.updated_at` 컬럼 없음, 수정 API 미노출 |
| 5 | 1계정 1브랜드 | `UNIQUE(brands.instagram_account_id)` |
| 6 | 프롬프트→결과 추적 | Langfuse Cloud + `generations.langfuse_trace_id` 연결 키 |

원칙 2가 가장 중요. **같은 덩어리(single blob) 에 스타일과 구도가 섞이지 않도록** 물리적으로 분리되어 있어야 한다.

---

## 2. 엔티티 관계

```
 BRANDS ──< REFERENCE_IMAGES
     ├──< GENERATIONS >── REFERENCE_IMAGES (nullable FK)
     │         └──< GENERATION_OUTPUTS
     │                     └──< GENERATED_UPLOADS
     └──│ INSTAGRAM_CONNECTIONS (1:1, 가변)
```

- `users` 테이블 없음 (회원가입 기능 없음, `brands` 가 최상위)
- `generation_prompts` 테이블 없음 (Langfuse 가 대체)
- `instagram_connections` 는 OAuth 토큰 전용 (brands 불변 원칙 방어)

---

## 3. 테이블

### 3.1 `brands` — 브랜드 + 스타일 (1:1 통합, 불변)

| 컬럼 | 타입 | 제약 | 비고 |
|------|------|------|------|
| `id` | UUID | PK | |
| `instagram_account_id` | str | UNIQUE, nullable | 온보딩 시엔 NULL, 인스타 연결 후 채움 |
| `instagram_username` | str | nullable | 표시용 (`@my_cafe`) |
| **— 브랜드 아이덴티티 —** | | | |
| `name` | str | NOT NULL | 브랜드 이름 |
| `color_hex` | str(7) | NOT NULL | `#RRGGBB` |
| `logo_path` | str | nullable | 로고 없으면 "이름 + 컬러" 로 대체 |
| **— 스타일 입력 (불변 박제) —** | | | |
| `input_instagram_url` | text | NOT NULL | 추구미 참고 링크 |
| `input_description` | text | NOT NULL | 가게 설명 |
| `input_mood` | text | NOT NULL | 가게 분위기 |
| **— 스타일 분석 결과 (불변) —** | | | |
| `style_prompt` | text | NOT NULL | GPT 분석 결과. 매 이미지/문구 생성에 주입 |
| `created_at` | datetime | NOT NULL | |

**핵심 제약**:
- `UNIQUE(instagram_account_id)` — 1계정 1브랜드
- `updated_at` **없음** → 스키마 레벨에서 "불변" 선언
- 수정 API 미노출: 서비스 계층은 `create()` / `get()` 만 제공, `update()` 없음

### 3.2 `reference_images` — 구도 전용 참조 (재사용)

| 컬럼 | 타입 | 제약 | 비고 |
|------|------|------|------|
| `id` | UUID | PK | |
| `brand_id` | UUID | FK → brands.id | |
| `source_output_id` | UUID | FK → generation_outputs.id, **UNIQUE** | 참조 원천 — MVP 는 기존 게시물만 참조 가능. UNIQUE 로 재사용 보장. |
| `path` | str | NOT NULL | `source_output.content_path` 복제 (분석·재참조 편의) |
| `composition_prompt` | text | NOT NULL | 카메라 앵글/프레이밍/배치 전용 (ReferenceAnalyzer 가 생성) |
| `created_at` | datetime | NOT NULL | |

**의도적 누락 컬럼**:
- `color_palette`, `mood`, `tone`, `style_hint` — **없음**. 실수로 브랜드 톤을 섞어 쓰는 여지를 DB 스키마가 원천 차단.

**생성 경로**:
- UI 의 reference gallery 에서 기존 게시물을 선택 → `_prepare_reference()` → `ReferenceImageService.upsert_by_source_output()`
- 같은 `source_output_id` 가 이미 있으면 재분석 없이 재사용 (UNIQUE 제약)
- 없으면 `ReferenceAnalyzer` (GPT Vision, 구도 전용 system prompt) 로 `composition_prompt` 생성 후 INSERT

**시스템 프롬프트 분리**:
- 구도 분석 system prompt 는 `brands.style_prompt` 생성용 system prompt 와 **물리적으로 다른 파일**. 색·톤 단어가 출력에 섞이지 않도록 유도.

### 3.3 `generations` — 생성 이벤트

상품 1개 당 게시글 1개 (광고문구 세트 + 이미지 1장).

| 컬럼 | 타입 | 제약 | 비고 |
|------|------|------|------|
| `id` | UUID | PK | |
| `brand_id` | UUID | FK → brands.id | |
| `reference_image_id` | UUID | FK → reference_images.id, nullable | |
| **— 상품 입력 —** | | | |
| `product_name` | str | NOT NULL | |
| `product_description` | text | NOT NULL | |
| `product_image_path` | str | nullable | 상품 원본 사진 |
| `goal` | str | NOT NULL | 신메뉴 출시 / 할인·이벤트 / ... |
| `tone` | str | NOT NULL | 기본 / 감성 / 고급 / 유머 / 심플 |
| `is_new_product` | bool | NOT NULL | |
| **— 추적 & 에러 —** | | | |
| `langfuse_trace_id` | str | nullable | Langfuse trace 연결 키 |
| `error_message` | text | nullable | 실패 시만 |
| `created_at` | datetime | NOT NULL | |

**삭제된 컬럼 (원래 제안에 있었음)**:
- `status` enum — 동기 처리라 pending/running 이 존재하지 않음. 실패 시 `error_message` 만으로 충분.
- `image_model` / `text_model` — Langfuse observation 에서 조회.
- `brand_snapshot` / `style_prompt_snapshot` / `composition_prompt_snapshot` — 브랜드 불변 원칙(#4)으로 FK 조회가 곧 당시 값. 참조 이미지도 분석 프롬프트 버전 변경이 잦지 않음 (Langfuse 가 버전 추적).
- `requested_at` / `completed_at` — `created_at` 으로 대체. 완료 시각은 Langfuse.
- `analyzer_prompt_version` — Langfuse prompt 버전 관리가 담당.

### 3.4 `generation_outputs` — 산출물

| 컬럼 | 타입 | 제약 | 비고 |
|------|------|------|------|
| `id` | UUID | PK | |
| `generation_id` | UUID | FK → generations.id | |
| `kind` | str | NOT NULL | `image` / `ad_copy` / `promo_sentence` / `story_copy` / `caption` / `hashtags` |
| `content_text` | text | nullable | 텍스트 산출물 |
| `content_path` | str | nullable | 이미지 파일 경로 |
| `created_at` | datetime | NOT NULL | |

**삭제된 컬럼**:
- `index` — 동일 kind 내 순번. 현재 UI 에서 순서가 의미 없고, 필요 시 `created_at` 으로 대체 가능.
- `revised_prompt` — Langfuse 에서 조회.

### 3.5 `instagram_connections` — Meta OAuth 토큰

`brands` 는 불변(원칙 #4)이라 **가변 데이터인 OAuth 토큰은 별도 테이블**에 둔다. 토큰 만료·재연결·해제 같은 상태 변경을 브랜드 본체와 격리.

| 컬럼 | 타입 | 제약 | 비고 |
|------|------|------|------|
| `id` | UUID | PK | |
| `brand_id` | UUID | FK → brands.id, UNIQUE | 1 Brand : 1 Connection |
| `access_token` | text | NOT NULL | Fernet 암호화 long-lived 토큰 |
| `token_type` | str | NOT NULL | 보통 `"long_lived"` |
| `token_expires_at` | datetime | nullable | UTC |
| `facebook_page_id` | str | nullable | |
| `facebook_page_name` | str | nullable | 수동 연결 시 `"수동 연결"` |
| `is_active` | bool | NOT NULL | 해제 시 `False` (soft delete) |
| `created_at` / `updated_at` | datetime | NOT NULL | 가변 — TimestampMixin 사용 |

**주의**:
- `instagram_account_id` / `instagram_username` 은 `brands` 에 둠 (이 값들은 사실상 불변, 토큰만 교체되어도 계정 ID 는 유지).
- `brands.instagram_account_id` 가 NULL 인 동안엔 이 테이블 레코드도 없음.

### 3.6 `generated_uploads` — 인스타 업로드 이력

| 컬럼 | 타입 | 제약 | 비고 |
|------|------|------|------|
| `id` | UUID | PK | |
| `generation_output_id` | UUID | FK → generation_outputs.id | 업로드된 산출물 (`kind=image` 이미지) |
| `kind` | str | NOT NULL | `feed` / `story` |
| `caption` | text | NOT NULL (feed) / 빈문자열 (story) | |
| `instagram_post_id` | str | nullable | 게시 성공 시만 |
| `posted_at` | datetime | nullable | 게시 성공 시만 |
| `created_at` | datetime | NOT NULL | |

한 `generation_output` (이미지) 이 피드와 스토리로 **각각 업로드** 될 수 있으므로 1:N.

---

## 4. 프롬프트 조립 흐름

```
 brands.style_prompt          ──┐
 reference_images              ──┤
   .composition_prompt (nullable)│
 generations.product_*          ─┼── build_image_prompt()  ──→  Langfuse trace 기록
 generations.goal/tone           │                               (input/output/metadata)
 브랜드 시각 자산 지시 (코드 상수)┘                                      │
                                                                       │
                                                              generations.langfuse_trace_id
```

**역할 분담**:

| 데이터 | 위치 | 비고 |
|--------|------|------|
| 비즈니스 엔티티 (브랜드·상품·참조·산출물·업로드) | **DB** | 관계 쿼리, UI 렌더링 |
| 최종 조립 프롬프트, 섹션별 parts, 모델명, 토큰/비용, 시스템 프롬프트 버전 | **Langfuse Cloud** | trace/observation/prompt 기능 |
| 연결 고리 | `generations.langfuse_trace_id` | UI에서 "이 생성의 추적 링크" 제공 가능 |

---

## 5. 온보딩 → 인스타 연결 순서

UX 상 온보딩을 먼저 노출하고, 실제 게시 시점에 인스타 연결을 요구한다.

```
1. 온보딩:  brands INSERT  (instagram_account_id = NULL)
2. 연결:    brands UPDATE  (instagram_account_id, instagram_username 채움)
3. 생성:    generations INSERT → generation_outputs INSERT
4. 게시:    generated_uploads INSERT  (인스타 게시 후)
```

1~2 사이에 이탈해도 brand 레코드는 남음 (미래 리마케팅 데이터).

---

## 6. 인덱스 / 제약 요약

| 테이블 | 유니크 | FK | 권장 인덱스 |
|--------|--------|-----|-------------|
| `brands` | `(instagram_account_id)` | — | — |
| `reference_images` | — | `brand_id` | `(brand_id, created_at DESC)` |
| `generations` | — | `brand_id`, `reference_image_id` | `(brand_id, created_at DESC)` |
| `generation_outputs` | — | `generation_id` | `(generation_id)` |
| `instagram_connections` | `(brand_id)` | `brand_id` | — |
| `generated_uploads` | — | `generation_output_id` | `(generation_output_id)` |

---

## 7. 마이그레이션 / 부트스트랩

Alembic 미사용. SQLAlchemy `Base.metadata.create_all(engine)` 로 부트스트랩한다 ([config/database.py:59](../config/database.py#L59)). 기존 `data/history.db` 는 본 리팩터 적용 전에 수동 삭제.

Alembic 도입은 멀티 환경(staging/prod) 분리 시점에 재검토 — [schema_future.md §4](schema_future.md#4-alembic-도입-시점).
