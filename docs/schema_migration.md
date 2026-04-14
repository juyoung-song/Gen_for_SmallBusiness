# 스키마 변경 정리 (구 → 신)

브랜치 `refactor/flow` 리팩터로 교체된 DB 스키마의 **바뀐 점**을 표로 정리한다.
확정 설계는 [schema.md](schema.md), 미래 후보는 [schema_future.md](schema_future.md).

## 1. 테이블 단위 변경

| 구분 | 구 스키마 | 신 스키마 | 비고 |
|------|-----------|-----------|------|
| 삭제 | `products` | — | 상품은 독립 테이블이 아니라 `generations.product_name/description/image_path` 필드로 흡수. 상품군은 `product_name` distinct 로 파생. |
| 삭제 | `brand_images` | — | 필드 일부를 `brands` 로 옮기고 이름 변경. |
| 삭제 | (없음) | — | `generation_prompts` 는 원래 제안됐으나 Langfuse 도입으로 아예 만들지 않음. |
| 신설 | — | `brands` | 아이덴티티(이름/로고/컬러) + 스타일(설명/분위기/style_prompt) 1:1 흡수. 불변. |
| 신설 | — | `reference_images` | 구도 전용 참조. `source_output_id UNIQUE` 로 재사용. |
| 신설 | — | `generations` | 상품별 생성 이벤트. Langfuse trace 연결 키 보유. |
| 신설 | — | `generation_outputs` | 이미지 + 텍스트 산출물 통합. |
| 교체 | `instagram_connections` (구) | `instagram_connections` (신) | OAuth 토큰 전용으로 축소. account_id/username 은 `brands` 로 이관. |
| 교체 | `generated_uploads` (구) | `generated_uploads` (신) | `product_id` → `generation_output_id` FK 로 재연결. `kind(feed/story)` 추가. |

---

## 2. 필드 단위 매핑 (핵심 테이블)

### 2.1 `brand_images` → `brands`

| 구 `brand_images` | 신 `brands` | 처리 |
|-------------------|-------------|------|
| `id` | `id` | UUID PK 유지 |
| `user_id` (str, default "default") | — | 삭제. `brands` 가 최상위 엔티티, `instagram_account_id UNIQUE` 로 사용자 식별 대체. |
| `content` | `style_prompt` | 이름 변경. GPT Vision 분석 결과. |
| `source_freetext` | `input_description` | 이름 변경. 사용자 자유 설명. |
| `source_reference_url` | `input_instagram_url` | 이름 변경. 추구미 인스타 URL. |
| `source_screenshots` (JSON list) | — | 삭제 (Tier 1). 캡처본은 파일로만 보존. |
| `brand_name` | `name` | 이름 변경. NOT NULL 로 격상. |
| `brand_color` | `color_hex` | 이름 변경. NOT NULL. |
| `brand_atmosphere` | `input_mood` | 이름 변경. NOT NULL 로 격상. |
| `brand_logo_path` | `logo_path` | 이름 변경. |
| — | `instagram_account_id` | **신규** (UNIQUE nullable). 인스타 연결 후 채움. |
| — | `instagram_username` | **신규** (nullable). 표시용. |
| `created_at` / `updated_at` (TimestampMixin) | `created_at` 만 | **불변 원칙 반영** — `updated_at` 제거. |

### 2.2 `products` → `generations` (흡수)

| 구 `products` | 신 `generations` | 처리 |
|---------------|------------------|------|
| `id` | — | 제거. Generation 당 product 정보를 중복 저장. |
| `name` | `product_name` | 필드명 변경, Generation 레코드에 박제. |
| `description` | `product_description` | 동일. |
| `raw_image_path` | `product_image_path` | 이름 변경. |
| `user_id` | (→ `generations.brand_id` 로 간접) | Brand 단위로 스코프. |
| `created_at` / `updated_at` | `created_at` 만 | append-only. |
| — | `goal` / `tone` / `is_new_product` | **신규**. 생성 요청 파라미터. |
| — | `brand_id` FK | **신규**. `brands.id` 참조. |
| — | `reference_image_id` FK nullable | **신규**. 구도 전용 참조. |
| — | `langfuse_trace_id` | **신규**. trace 추적 키. |
| — | `error_message` | **신규**. 실패 시만. |

### 2.3 `instagram_connections` (구 → 신)

| 구 컬럼 | 신 컬럼 | 처리 |
|---------|---------|------|
| `id` | `id` | 유지. |
| `brand_config_id` | `brand_id` | 이름 변경. FK 대상 동일 (`brands.id`). |
| `access_token` (Fernet) | `access_token` | 유지. |
| `token_type` | `token_type` | 유지. |
| `token_expires_at` | `token_expires_at` | 유지. |
| `instagram_account_id` | — | **삭제** → `brands.instagram_account_id` 로 이관 (불변 식별자이므로 연결 본체가 아닌 브랜드에 귀속). |
| `instagram_username` | — | **삭제** → `brands.instagram_username` 로 이관. |
| `facebook_page_id` / `facebook_page_name` | 동일 | 유지. |
| `is_active` | 유지 | soft delete 용. |
| `created_at` / `updated_at` | 유지 (TimestampMixin) | 가변 데이터이므로 `updated_at` 보존. |

### 2.4 `generated_uploads` (구 → 신)

| 구 컬럼 | 신 컬럼 | 처리 |
|---------|---------|------|
| `id` | `id` | 유지. |
| `product_id` FK → `products.id` | `generation_output_id` FK → `generation_outputs.id` | **재연결**. 상품이 아닌 산출물(이미지)에 업로드가 묶임. |
| `image_path` | — | **삭제** (`GenerationOutput.content_path` 에서 가져옴). |
| `caption` | `caption` | 유지. story 는 빈 문자열. |
| `goal_category` / `goal_freeform` | — | **삭제** (`Generation.goal` 로 흡수). |
| — | `kind` | **신규** (`feed` / `story`). |
| `instagram_post_id` / `posted_at` | 동일 | 유지. |
| `created_at` / `updated_at` (TimestampMixin) | `created_at` 만 | append-only. |

---

## 3. 원칙 단위 변경

| 원칙 | 구 구조 | 신 구조 |
|------|---------|---------|
| 브랜드 식별 | `brand_images.user_id="default"` (사실상 단일 사용자 하드코딩) | `brands.instagram_account_id UNIQUE` (1계정 1브랜드, nullable 연결 전) |
| 브랜드 수정 | TimestampMixin 으로 `updated_at` 자동 갱신 허용 | **`updated_at` 제거** — 스키마 레벨에서 불변 선언 |
| 스타일/구도 분리 | 별도 테이블 없음 (구도 개념 없음) | `brands.style_prompt` vs `reference_images.composition_prompt` 물리적 분리 |
| 참조 이미지 톤 차단 | — | `reference_images` 에 color/mood/tone 컬럼 의도적 누락 |
| 프롬프트→결과 추적 | 미구현 | Langfuse Cloud + `generations.langfuse_trace_id` |
| 상품 중복 관리 | `products` 테이블 UNIQUE 없음 (이름 충돌 가능) | `product_name` 으로 distinct 그룹핑, DB 제약 없이 서비스 레벨에서 처리 |

---

## 4. 실제 데이터 저장 변화 예시

신규 스키마로 온보딩 → 인스타 연결 → 상품 생성 → 게시 → 재생성 → 참조 반영 시나리오의 현재 DB 상태:

| 테이블 | 레코드 수 | 설명 |
|--------|-----------|------|
| `brands` | 1 | `goorm` / `#5562EA` / `@wonbywondev` / `instagram_account_id=17841433263101282` |
| `instagram_connections` | 1 | 해당 brand 의 Fernet 암호화된 long-lived 토큰 (60일) |
| `generations` | 3 | 같은 `product_name="따뜻한 아메리카노"` 를 신상품 1회 + 기존상품 재생성 2회 |
| `generation_outputs` | 27 | generation 당 9개 (image 1 + ad_copy 3 + promo 2 + story 3) |
| `reference_images` | 1 | 2번째 generation 의 이미지가 3번째 생성의 참조로 재분석 · upsert |
| `generated_uploads` | 2 | feed 1건 게시 완료 + 추가 업로드 |

---

## 5. 마이그레이션 메모

- 기존 DB 는 보존 없이 삭제 후 `Base.metadata.create_all` 로 신 스키마 생성 (MVP 단계, 사용자 실데이터 아직 없음).
- Alembic 미도입. staging/prod 분리 시점에 baseline stamp 로 도입 예정 ([schema_future.md §3](schema_future.md#3-alembic-도입-시점)).
- legacy 테스트(`test_brand_image.py`, `test_product.py` 등) 는 모두 삭제 후 신 스키마 기준으로 재작성 (CP6 참고).
