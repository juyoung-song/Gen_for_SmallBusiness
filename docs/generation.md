# 광고 생성 · 참조 이미지 · 업로드 · 히스토리

> Legacy note: 이 문서는 `refactor/flow` Streamlit `app.py` 기준 실행 경로를 많이 포함한다.
> 현재 모바일 PWA 생성/업로드 흐름은 [mobile_worker_workflow.md](mobile_worker_workflow.md)를 우선한다.

현 브랜치(`refactor/flow`) 코드 기준의 **실제 실행 경로** 문서.

다루는 범위:

1. **광고 생성** — 텍스트 / 이미지 / 결합 3종, 프롬프트 조립, DB 저장(Generation + Outputs)
2. **참조 이미지** — reference gallery 선택 → 구도 분석(Vision) → ImageGenerationRequest 주입
3. **피드 캡션 생성** — Instagram preview + 편집 + 게시
4. **스토리 이미지 합성** — 9:16 PIL 로컬 합성 (LLM 호출 없음)
5. **인스타 업로드** — Meta Graph API v19.0, feed/story
6. **히스토리 탭** — 게시된 `generated_uploads` 목록

관련 문서: [onboarding.md](onboarding.md), [schema.md](schema.md).

---

## 1. 광고 생성

### 1.1 개요

한 번의 생성 요청은:

- **Generation 1건** + **GenerationOutput N건** 을 단일 트랜잭션으로 INSERT
- Langfuse 루트 span 아래에 OpenAI 호출들이 자식 observation 으로 묶여 `langfuse_trace_id` 1개로 추적
- 참조 이미지가 있으면 구도 분석 후 `Generation.reference_image_id` FK 로 연결

3개 경로:

| 타입     | 함수                         | OpenAI 호출 수             | Langfuse 루트 span        |
| -------- | ---------------------------- | -------------------------- | ------------------------- |
| 텍스트만 | `_run_text_generation`     | 1                          | `generation.text_only`  |
| 이미지만 | `_run_image_generation`    | 2 (번역 + 이미지)          | `generation.image_only` |
| 결합     | `_run_combined_generation` | 3 (텍스트 + 번역 + 이미지) | `generation.combined`   |

### 1.2 진입 — 탭 "새로 만들기"

[app.py:813~1048](../app.py#L813) `tab_create` 블록. 4개 섹션:

**섹션 1: 상품 정보**

- 신상품 토글 `is_new_product`
- 기존 상품 드롭다운: `GenerationService.list_products(brand_id)` → `ProductGroup` 리스트
  - [services/generation_service.py:127](../services/generation_service.py#L127) — `product_name` 기반 distinct 그룹핑, `generation_count` 포함
- 기존 상품 선택 시 이미지 미리보기 (CP9) — `Path(existing_raw_image_path).exists()` 검증
- 신상품 모드면 새 이미지 파일 업로더

**섹션 2: 생성 타입**

- `st.radio` 3종: 홍보 글만 / 이미지만 / 결합

**섹션 3: 옵션**

- **광고 목적 칩** (CP11) — 토글 OFF 면 "신메뉴 출시" 옵션 제외
  ```python
  if is_new_product:
      goal_options = list(GOAL_CATEGORIES)
  else:
      goal_options = [c for c in GOAL_CATEGORIES if c != "신메뉴 출시"]
  ```

  이전 선택값이 새 목록에 없으면 세션 키 삭제 → StreamlitException 방지
- 자유 텍스트
- 톤 / 스타일 — `TONE_STYLE_DISPLAY_MAP`

**섹션 4: 참조 이미지 갤러리**

- [app.py:930](../app.py#L930) `render_reference_gallery()` 호출 (§2 참고)
- 반환: `(paths, output_ids)` 튜플

### 1.3 생성 버튼 클릭 이후

```
"🚀 만들기" 클릭
  │
  ├─ 폼 검증
  │    신상품이면 이름/설명/이미지 필수
  │    기존 상품이면 selected_product 필수
  │
  ├─ 상품 이미지 준비
  │    신상품  → save_to_staging(업로드 바이트)  → current_product_image_path
  │    기존    → existing_raw_image_path 그대로
  │
  ├─ 참조 첫 번째 선택만 세션 저장
  │    current_reference_source_output_id = selected_reference_output_ids[0] or None
  │
  └─ 생성 타입별 분기
       ├─ _run_text_generation(...)
       ├─ _run_image_generation(..., reference_image_paths)
       └─ _run_combined_generation(..., reference_image_paths)
```

### 1.4 실행 플로우 — `_run_combined_generation`

가장 복잡한 경로이므로 기준으로 설명. 다른 둘은 단순 축소형.

```
_run_combined_generation(name, desc, goal, tone, style, ..., reference_image_paths)
  │
  ├─ error_message / error_exception 리셋
  ├─ last_request 세션 저장 (재생성 버튼용)
  │
  ├─ _prepare_reference(current_reference_source_output_id)  (app.py:496)
  │     │  참조 선택 있으면 실행 (없으면 None, "")
  │     │
  │     └─ ReferenceImageService.upsert_by_source_output(
  │           source_output_id, analyzer=ReferenceAnalyzer(settings))
  │           │
  │           ├─ 기존 ReferenceImage 있음  → 재분석 없이 그대로 반환 (캐시 히트)
  │           │
  │           └─ 신규:
  │              ├─ GenerationOutput.kind="image" 검증
  │              ├─ ReferenceAnalyzer.analyze(path)
  │              │    system prompt = build_composition_analysis_prompt()
  │              │       (구도 전용 — 색/무드/스타일 단어 금지)
  │              │    OpenAI chat.completions.create(
  │              │       name="reference.vision_composition",
  │              │       model=TEXT_MODEL)
  │              └─ reference_images INSERT (brand_id 역추적, source_output_id UNIQUE)
  │     → (ref_id, composition_prompt)
  │
  ├─ session_state.current_reference_image_id = ref_id
  │
  ├─ with _langfuse_trace_span("generation.combined"):          ← 루트 span 시작
  │    │
  │    ├─ [Step 1] 텍스트 생성
  │    │     req_t = TextGenerationRequest(
  │    │              ...,
  │    │              brand_prompt,                  ← onboarding 의 style_prompt
  │    │              is_new_product,
  │    │              reference_analysis="")          ← 텍스트엔 구도 주입 안 함
  │    │     text_service.generate_ad_copy(req_t)
  │    │        └─ select_text_backend()  →  OpenAIGPTBackend
  │    │             utils/prompt_builder.py:51  build_text_prompt()
  │    │               system: [[브랜드 가이드라인]] + [[상품 상태 지침]] + [[글 톤 지침]] + 생성 규칙
  │    │               user:   상품 정보 + 응답 형식 ([광고 문구]/[홍보 문장]/[스토리 카피])
  │    │             OpenAI chat.completions.create(
  │    │               name="text.generate_ad_copy",
  │    │               messages=[system, user])
  │    │     → TextGenerationResponse (ad_copies 3, promo_sentences 2, story_copies 3)
  │    │     → session_state.text_result = response.model_dump()
  │    │
  │    ├─ [Step 2] 이미지 생성 (hint = 첫 번째 ad_copy)
  │    │     req_i = ImageGenerationRequest(
  │    │              ...,
  │    │              prompt = res_t.ad_copies[0],
  │    │              brand_prompt,
  │    │              reference_analysis = composition_prompt)   ← 구도 주입
  │    │     image_service.generate_ad_image(req_i)
  │    │        ├─ _resolve_reference_image_data()  (reference_image_paths[0] 바이트 로드)
  │    │        ├─ select_image_backend(has_reference)
  │    │        │    mock / HF_REMOTE_API / HF_LOCAL (IP-Adapter/Img2Img/Hybrid)
  │    │        │
  │    │        ├─ (MOCK 아니면) _translate_to_english(request)   ← 한→영 번역
  │    │        │    build_image_prompt()  (한국어 조립)
  │    │        │    OpenAI chat.completions.create(
  │    │        │      name="image.translate_ko_to_en",
  │    │        │      system: "Translate ... under 60 words, comma-separated")
  │    │        │
  │    │        └─ backend.generate(request)   →  image_data bytes
  │    │     → _stash_generated_image(bytes)
  │    │         save_to_staging → current_generated_image_path
  │    │     → session_state.image_result
  │    │
  │    └─ _capture_langfuse_trace_id()
  │         session_state._pending_langfuse_trace_id = client.get_current_trace_id()
  │
  └─ _save_generation_record(text_result, image_bytes)
       │
       ├─ GenerationService.create_with_outputs(
       │     brand_id,
       │     reference_image_id = current_reference_image_id,
       │     product_name / description / image_path,
       │     goal / tone / is_new_product,
       │     outputs = [image + ad_copy×3 + promo×2 + story×3],
       │     langfuse_trace_id = _pending_langfuse_trace_id)
       │
       ├─ generations INSERT (1건)
       ├─ generation_outputs INSERT (N건)
       │
       └─ session_state.current_generation_output_id = image output.id
          session_state.current_generation_id       = gen.id
```

실패 시 `logger.exception` + `st.error` + `st.exception` expander (CP7).

### 1.5 프롬프트 조립

#### `build_text_prompt` — [utils/prompt_builder.py:51](../utils/prompt_builder.py#L51)

반환: `(system_prompt, user_prompt)` 튜플.

**system 구조**

1. "당신은 대한민국 최고의 브랜드 전략가이자 카피라이터입니다."
2. `[[브랜드 가이드라인]]` ← `brand_prompt` (비어있으면 내장 `_BRAND_CUES`)
3. `[[상품 상태 지침]]` — is_new_product 분기
4. `[[글 톤 지침]]` — `_STYLE_GUIDE[style]` (5종)
5. 생성 규칙 5가지

**user 구조**
상품명 / 설명 / 상태 / 홍보 목적 + (있으면) reference_analysis + (있으면) image_hint + 응답 형식(광고/홍보/스토리 섹션).

응답 파싱은 [backends/openai_gpt.py:98](../backends/openai_gpt.py#L98) `_parse_response`. 실패 시 폴백 메시지.

#### `build_image_prompt` — [utils/prompt_builder.py:150](../utils/prompt_builder.py#L150)

한국어 조립 결과(1문자열) → 한→영 번역 → 이미지 백엔드 전달.

블록 순서:

1. `Brand guidelines (MUST follow): {brand_prompt}` ← 맨 앞 + `MUST follow` 명령
2. 주제 선언: `A professional commercial advertisement visual concept for '{product_name}'.`
3. (참조 있으면) `Respect the composition and color scheme of the provided reference image.`
4. (`reference_analysis` 있으면) `Selected reference analysis: {...}. Use this as the primary visual synthesis...`
5. 상품 상태 가이드 (신상품 vs 기존)
6. `Promotional Context: {goal}.`
7. `Visual Strategy: {goal_visual_map[goal]}` — 목적별 영어 지시문 6종
8. `Style: {_IMAGE_STYLE_MAP[style]}`
9. `Inspiration: {ad_copy} {description}`
10. 공통 꼬리말: `Clean composition, high-end product photography, commercial lighting. ... no text on image.`

#### 한→영 번역

[services/image_service.py:146](../services/image_service.py#L146):

```python
client.chat.completions.create(
    name="image.translate_ko_to_en",
    messages=[
        {"role": "system", "content":
          "Translate the given Korean description into a concise English prompt "
          "for Stable Diffusion / FLUX. STRICT LIMIT: under 60 words "
          "(comma-separated keywords). Output ONLY the English keywords."},
        {"role": "user", "content": raw_prompt},
    ])
```

결과가 `request.prompt` 를 덮어쓰고 백엔드에 들어감.

### 1.6 데이터 저장

#### `Generation` 테이블

[models/generation.py](../models/generation.py)

| 필드                                                                | 비고                   |
| ------------------------------------------------------------------- | ---------------------- |
| `id` UUID PK                                                      |                        |
| `brand_id` FK → brands                                           |                        |
| `reference_image_id` FK → reference_images (nullable)            |                        |
| `product_name` / `product_description` / `product_image_path` | 상품 정보 (중복 저장)  |
| `goal` / `tone` / `is_new_product`                            | 생성 파라미터          |
| `langfuse_trace_id`                                               | Langfuse Cloud 연결 키 |
| `error_message`                                                   | 실패 시만              |
| `created_at`                                                      |                        |

#### `GenerationOutput` 테이블

[models/generation_output.py](../models/generation_output.py)

| 필드                 | 비고                                                                                       |
| -------------------- | ------------------------------------------------------------------------------------------ |
| `id` UUID PK       |                                                                                            |
| `generation_id` FK |                                                                                            |
| `kind`             | `image` / `ad_copy` / `promo_sentence` / `story_copy` / `caption` / `hashtags` |
| `content_text`     | 텍스트 산출물 (이미지면 NULL)                                                              |
| `content_path`     | 이미지 파일 경로 (텍스트면 NULL)                                                           |
| `created_at`       |                                                                                            |

한 Generation 당 9개 output 기본 (image 1 + ad_copy 3 + promo 2 + story 3). 캡션/해시태그는 별도 생성 시 추가.

#### `GenerationService.create_with_outputs`

[services/generation_service.py:52](../services/generation_service.py#L52). 단일 트랜잭션:

1. Generation `session.add` + `flush` (id 확보)
2. GenerationOutput N개 `session.add`
3. `commit` + `refresh(attribute_names=["outputs"])` — 호출자가 즉시 `gen.outputs` 접근 가능하도록

---

## 2. 참조 이미지

### 2.1 UI — `render_reference_gallery`

[ui/reference_gallery.py:29](../ui/reference_gallery.py#L29).

```
render_reference_gallery()  →  (selected_paths, selected_output_ids)
  │
  ├─ _fetch_published_pairs()
  │    UploadService.list_published(brand_id=None 전체)
  │       GeneratedUpload ⨝ GenerationOutput (instagram_post_id != NULL)
  │       ORDER BY posted_at DESC
  │
  ├─ 중복 제거 (CP8)
  │    seen_output_ids set — 같은 이미지가 feed/story 여러 번 올라와도 1장만 표시
  │
  ├─ 3열 그리드, 최대 24장
  │    각 카드: st.image(output.content_path) + 캡션 미리보기 + 체크박스
  │    key = f"ref_select_{output.id}"
  │
  └─ 선택된 output 의 (content_path, id) 리스트 반환
```

### 2.2 분석 — `_prepare_reference`

[app.py:496](../app.py#L496). 생성 버튼 직후 호출.

```
_prepare_reference(source_output_id)  →  (ref_id, composition_prompt)
  │
  ├─ source_output_id is None  →  (None, "")
  │
  └─ ReferenceImageService.upsert_by_source_output(
        source_output_id,
        analyzer=ReferenceAnalyzer(settings))
        │
        ├─ get_by_source_output(source_output_id)  ─ 있음  →  그대로 반환 (재분석 스킵)
        │
        └─ 없음:
           ├─ GenerationOutput 조회, kind="image" 검증
           ├─ Generation 조회 (brand_id 역추적)
           ├─ analyzer.analyze(Path(output.content_path))
           │    build_composition_analysis_prompt()  ← 구도 전용 system
           │    OpenAI chat.completions.create(
           │      name="reference.vision_composition",
           │      messages=[user + base64 image])
           │    → composition_prompt (영문, 40단어 이하)
           │
           └─ reference_images INSERT
                (brand_id, source_output_id UNIQUE, path, composition_prompt)
```

### 2.3 구도 전용 system prompt

[services/reference_service.py:32](../services/reference_service.py#L32) `build_composition_analysis_prompt()`:

포함 항목:

- camera angle / framing / subject placement / depth of field / arrangement / orientation

**STRICT RULES** (절대 금지):

- 색감·팔레트·무드·분위기·조명 스타일·톤·브랜드 느낌
- 실제 상품 묘사 (`croissant` 등) — 역할(`central subject`) 만
- 재질·마감·미학 형용사 (minimal/rustic/modern 등)

출력 예시: `overhead flat-lay, central subject, symmetric props around, shallow depth`

스키마 레벨 방어선과 맞물림: `reference_images` 테이블엔 color/mood/tone 컬럼이 **의도적으로 없음**.

### 2.4 주입

- **이미지 생성 프롬프트에**: `ImageGenerationRequest.reference_analysis = composition_prompt`. `build_image_prompt` 의 4번 블록 `Selected reference analysis:` 로 들어감.
- **텍스트·캡션에는 주입 금지** — 원칙상 텍스트 톤과 섞이면 안 됨 (CP5 주석 참고).
- `Generation.reference_image_id` FK 로 영속화 → 히스토리에서 "이 생성은 어떤 참조를 썼는가" 추적 가능.

---

## 3. 피드 캡션 생성

### 3.1 흐름

[app.py:1152](../app.py#L1152) "📸 인스타 피드 게시물 만들기" 버튼:

```
CaptionGenerationRequest(
  product_name, description,
  ad_copies = text_result["ad_copies"],
  style = req_info["text_tone"],
  brand_prompt,
  is_new_product,
  reference_analysis = "")              ← 캡션엔 구도 주입 금지 (정책)
  │
  ↓
CaptionService.generate_caption(req)
  services/caption_service.py:39
  OpenAI chat.completions.create(
    name="caption.generate",
    messages=[system, user])
  │
  ↓
파싱: "[본문]" / "[해시태그]" 섹션 분리
  │
  ↓
CaptionGenerationResponse(caption, hashtags)
  → session_state.caption_result
```

### 3.2 system prompt 핵심

[services/caption_service.py:63](../services/caption_service.py#L63):

- 역할: 인스타 SNS 마케터
- **사실 기반 제한** — 확인되지 않은 배경/소품/행동/장면 지어내기 금지
- **고객 일상 예시 1문장 필수** — "내 이야기 같다" 느낌
- 본문 2~4문단, 문단 간 줄 띄우기
- 이모지 1~3개 필수, 남발 금지
- 상품 상태("신상품"/"기존 상품") 직접 언급 금지 — 맥락으로만
- `brand_prompt` 반영, `reference_analysis` 는 문체 참고만 (새 사실 금지)

### 3.3 Instagram preview + 업로드

[app.py:243](../app.py#L243) `render_instagram_preview_and_upload`.

```
왼쪽 목업: 헤더(아바타+유저명+Sponsored) → 이미지 → ❤️💬↗️ → 캡션 → 해시태그
오른쪽 편집: text_area(캡션) + text_area(해시태그) + "🚀 업로드" 버튼
  │
  ├─ apply_user_token(settings, brand)   ← 가드, 실패면 RuntimeError
  │   (onboarding.md §2.4 참고)
  │
  ├─ InstagramService(settings)
  │   .upload_real(image_bytes, f"{caption}\n\n{tags}")  (또는 upload_mock)
  │   제너레이터 패턴: status_msg 스트리밍
  │     "FreeImage 업로드 중" → "미디어 생성" → status 폴링 → "media_publish" → "DONE"
  │
  └─ "DONE" 수신 시:
       _persist_generated_upload(
         kind="feed",
         caption=f"{caption}\n\n{tags}",
         post_id=ig_svc.last_post_id,
         posted_at=ig_svc.last_posted_at)
       st.balloons()
```

Meta 미디어 상태 폴링은 [services/instagram_service.py:130-180](../services/instagram_service.py#L130-L180) 최대 30초, GET 실패 시 지수 백오프 3회 재시도.

---

## 4. 스토리 이미지 합성

### 4.1 흐름

[app.py:1173](../app.py#L1173) "📱 인스타 스토리 만들기" 버튼 → `show_story_ui=True` → [app.py:343](../app.py#L343) `render_instagram_story_preview_and_upload`.

```
오른쪽: st.radio 로 text_result["story_copies"] 3개 중 1개 선택
  │
  └─ "✨ 선택한 문구로 스토리 이미지 만들기" 버튼
       ImageService.compose_story_image(image_bytes, selected_copy)
         services/image_service.py:253
         순수 PIL 합성, LLM 호출 없음:
           · 1080×1920 캔버스
           · 원본 → Gaussian Blur(60) 배경
           · 중앙 960×960 카드 (원본 LANCZOS resize) + 10px 반투명 그림자
           · y=1550 부터 텍스트 80px 줄간격, 중앙정렬, 흰색
         폰트: settings.STORY_FONT_PATHS 왼쪽부터, 실패 시 PIL 기본 폰트
       → session_state.story_result (PNG 바이트)
       → session_state.story_text

왼쪽 목업: 스토리 헤더 + 합성 이미지 미리보기
  │
  └─ "🚀 위 스토리 바로 올리기"
       apply_user_token(settings, brand)
       ig_svc.upload_story(story_result)   (mock 이면 upload_mock(..., is_story=True))
       "DONE" 수신 시 st.success + st.balloons
```

스토리는 **`_persist_generated_upload` 호출 안 함** — post_id 추적 불필요하다고 현재 정책.

Meta API 차이: [services/instagram_service.py:114-116](../services/instagram_service.py#L114-L116) — `media_type=STORIES`, caption 필드 절대 포함 금지.

---

## 5. 인스타 업로드 공통 — `_persist_generated_upload`

[app.py:447](../app.py#L447). 피드 게시 성공 시만 호출.

```
_persist_generated_upload(kind, caption, post_id, posted_at)
  │
  ├─ current_generation_output_id 확인
  │    없으면 RuntimeError — 텍스트 전용 생성 후거나 저장 실패
  │
  ├─ UploadService.create(
  │     generation_output_id,
  │     kind,                          ← "feed" / "story"
  │     caption)
  │   → generated_uploads INSERT (instagram_post_id=NULL)
  │
  └─ UploadService.mark_posted(
        upload_id, instagram_post_id, posted_at)
     → instagram_post_id / posted_at UPDATE
```

실패 시 `logger.exception` + 세션의 `current_generation_output_id` 를 None 으로 리셋 (다음 업로드 차단).

### `generated_uploads` 테이블

[models/generated_upload.py](../models/generated_upload.py)

| 필드                                              | 비고                                        |
| ------------------------------------------------- | ------------------------------------------- |
| `id` UUID PK                                    |                                             |
| `generation_output_id` FK → generation_outputs |                                             |
| `kind`                                          | `feed` / `story`                        |
| `caption`                                       | story 는 빈 문자열 (현재 경로는 저장 안 함) |
| `instagram_post_id`                             | 게시 성공 시만                              |
| `posted_at`                                     | 게시 성공 시만                              |
| `created_at`                                    |                                             |

---

## 6. 히스토리 탭

[app.py:1200~1252](../app.py#L1200). "🗂️ 예전에 만든 홍보물 보기" 탭.

```
tab_archive
  │
  ├─ UploadService.list_published(brand_id=_loaded_brand.id)
  │    → [(GeneratedUpload, GenerationOutput), ...]   (instagram_post_id != NULL)
  │
  ├─ 각 pair 마다 GenerationService.get_with_outputs(output.generation_id)
  │    → [(upload, output, generation), ...]
  │
  └─ st.expander 로 카드 표시:
       제목:  📸 {gen.product_name} — {gen.goal} ({upload.kind}) · {posted_at}
       내용:  이미지 (output.content_path)
              | 상품명 / 광고 목적 / 업로드 종류 / 캡션 code block / instagram_post_id
```

---

## 7. 세션 키 맵 (생성 관련)

| 키                                                                                          | 설정 시점                      | 용도                                     |
| ------------------------------------------------------------------------------------------- | ------------------------------ | ---------------------------------------- |
| `is_new_product`                                                                          | UI 토글                        | 프롬프트 분기 + 목적 칩 필터             |
| `last_request`                                                                            | `_run_*_generation` 시작     | 재생성 버튼                              |
| `current_product_image_path`                                                              | 상품 이미지 staging 후         | Generation.product_image_path            |
| `current_generated_image_path`                                                            | `_stash_generated_image`     | GenerationOutput.content_path            |
| `current_reference_source_output_id`                                                      | 참조 선택                      | `_prepare_reference` 입력              |
| `current_reference_image_id`                                                              | `_prepare_reference` 반환    | Generation.reference_image_id FK         |
| `current_generation_id`                                                                   | `_save_generation_record`    | 히스토리 조회                            |
| `current_generation_output_id`                                                            | 동일                           | UploadService FK — 텍스트 전용이면 None |
| `_pending_langfuse_trace_id`                                                              | `_capture_langfuse_trace_id` | Generation.langfuse_trace_id             |
| `text_result` / `image_result` / `caption_result` / `story_result` / `story_text` | 각 생성 완료 시                | UI 렌더 입력                             |
| `error_message` / `error_exception`                                                     | 예외 발생                      | UI 표시 + expander traceback             |

---

## 8. Langfuse Observation 이름 맵

루트 span + 자식 observation 트리 구조로 찍힘.

| 루트 span                 | 자식 observation                             | 파일:라인                                                                 |
| ------------------------- | -------------------------------------------- | ------------------------------------------------------------------------- |
| `generation.text_only`  | `text.generate_ad_copy`                    | [backends/openai_gpt.py:77](../backends/openai_gpt.py#L77)                   |
| `generation.image_only` | `image.translate_ko_to_en` + 이미지 백엔드 | [services/image_service.py:146](../services/image_service.py#L146)           |
| `generation.combined`   | 위 2개 +`text.generate_ad_copy`            | —                                                                        |
| (루트 없음 — 개별 trace) | `reference.vision_composition`             | [services/reference_service.py:77](../services/reference_service.py#L77)     |
| (루트 없음 — 개별 trace) | `onboarding.vision_brand_style`            | [services/onboarding_service.py:160](../services/onboarding_service.py#L160) |
| (루트 없음 — 개별 trace) | `caption.generate`                         | [services/caption_service.py:111](../services/caption_service.py#L111)       |

캡션/참조 분석/온보딩 Vision 은 생성 이벤트와 별개라 별도 trace. Generation 이 실행될 때만 루트 span 으로 묶음.

---

## 9. 에러 처리 (CP7)

모든 생성/업로드 경로는 동일 패턴:

```python
except Exception as e:
    logger.exception("컨텍스트")
    st.session_state.error_message = f"❌ ... (타입: {type(e).__name__} / 상세: {e})"
    st.session_state.error_exception = e
```

에러 표시 지점 [app.py:1014~](../app.py#L1014):

```python
if st.session_state.error_message:
    st.error(st.session_state.error_message)
    exc = st.session_state.get("error_exception")
    if exc is not None:
        with st.expander("🔍 기술 상세 (디버깅)", expanded=False):
            st.exception(exc)
```

디버깅 우선 — 실패 시 **조용히 지나가지 않고** 콘솔 로그 + UI stacktrace.

---

## 10. DB 관계 한눈에

```
Brand (1)
  ├─ ReferenceImage (N, brand_id FK)
  │     └─ source_output_id UNIQUE → GenerationOutput (역참조)
  │
  └─ Generation (N, brand_id FK)
        ├─ reference_image_id FK → ReferenceImage (nullable)
        └─ GenerationOutput (N, generation_id FK)
              └─ GeneratedUpload (N, generation_output_id FK)
                    · kind="feed" / "story"
                    · instagram_post_id / posted_at (게시 성공 시)
```

생성 이벤트 1회 = Generation 1 + GenerationOutput 9 (기본). 업로드가 여러 번이면 GeneratedUpload 가 쌓이고, 참조 이미지 재사용 시 ReferenceImage 는 `source_output_id UNIQUE` 로 1건만 유지.
