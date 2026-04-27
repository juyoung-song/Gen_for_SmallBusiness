# 온보딩 플로우

2026-04-16 현재 모바일 PWA 기준의 온보딩 보충 문서다.

주의: 아래 본문에는 `refactor/flow` Streamlit 구현 설명이 일부 남아 있다. 현재 운영 진입점은 `app.py`가 아니라 `mobile_app.py + stitch/*`이며, 이 문서에서는 먼저 현재 모바일 기준 변경점을 정리한다.

1. **브랜드 온보딩/재분석** — 사용자 입력 + 인스타 프로필 캡처 + GPT Vision 분석 → `brands` 생성 또는 제한적 갱신
2. **인스타 OAuth 연결** — Meta v19.0 OAuth → long-lived token → `instagram_connections` INSERT + `brands` UPDATE

연관 문서:
- 생성 플로우(광고/업로드): [generation.md](generation.md)
- 모바일/VM 운영 플로우: [mobile_worker_workflow.md](mobile_worker_workflow.md)
- 최신 운영 기준: [../README.md](../README.md)

---

## 1. 브랜드 온보딩

### 1.0 현재 모바일 PWA 기준 요약

현재 온보딩 저장 경로는 `POST /api/mobile/onboarding/complete`다.

입력 소스:
- 브랜드 이름, 대표 색상, 분위기 키워드, 직접 설명
- 로고 이미지
- 사용자가 직접 업로드한 스크린샷
- 선택적으로 Instagram URL

Instagram URL 캡처 순서:
1. `INSTAGRAM_CAPTURE_WORKER_URL`이 있으면 Mac 로컬 캡처 워커에 `/capture` 요청을 보낸다.
2. Mac 워커는 로그인된 Playwright persistent profile로 Instagram을 열고 스크린샷을 찍어 `data_url`로 반환한다.
3. VM `mobile_app.py`가 반환 이미지를 `/srv/brewgram/data/staging/`에 저장한다.
4. Mac 워커가 실패하거나 설정이 없으면 VM의 `backends/insta_capture.py` fallback을 시도한다.
5. 캡처 직후 `HTTP ERROR 429`, `accounts/login`, `This page isn... working` 같은 상태가 감지되면 해당 이미지는 분석에 넣지 않는다.

UX 기준:
- Instagram URL보다 직접 스크린샷 업로드를 우선 추천한다.
- Instagram URL 캡처가 실패해도 사용자가 입력한 설명과 업로드한 이미지가 있으면 온보딩은 계속 진행한다.
- 3페이지의 “이렇게 브랜드를 이해했어요” 문구는 최종 저장될 `brands.style_prompt` 미리보기다.
- 현재는 같은 엔드포인트로 기존 브랜드 정보를 다시 분석해 덮어쓸 수 있다. 다만 브랜드 수정 기능은 아직 완전히 제품화된 상태는 아니고, 특히 로고 유지/교체/제거 정책은 계속 정리 중이다.
- 로고를 새로 올리지 않으면 기존 `logo_path`를 우선 재사용한다. 기존 로고도 없으면 워드마크 PNG를 자동 생성해 저장한다.

관련 파일:
- [mobile_app.py](../mobile_app.py)
- [scripts/instagram_capture_worker.py](../scripts/instagram_capture_worker.py)
- [backends/insta_capture.py](../backends/insta_capture.py)
- [services/onboarding_service.py](../services/onboarding_service.py)
- [stitch/1./code.html](../stitch/1./code.html)
- [stitch/2./code.html](../stitch/2./code.html)
- [stitch/3./code.html](../stitch/3./code.html)

### 1.1 개요

`brands` 는 서비스의 최상위 엔티티다. 초기 설계는 불변 모델에 가까웠지만, 현재 모바일 PWA 흐름에서는 같은 brand row 를 유지한 채 `name`, `color_hex`, `logo_path`, `style_prompt` 를 다시 분석해 갱신할 수 있다.

다만 이 변경은 "브랜드 수정 기능이 완성됐다"는 뜻은 아니다. 현재 구현은 생성/업로드/인스타 연결을 끊지 않고 브랜드 입력값을 다시 반영할 수 있게 확장성을 열어둔 수준이며, 이력 관리와 로고 제거 정책은 아직 완전히 정리되지 않았다.

### 1.2 진입 & 라우팅

- 모바일 앱은 `GET /api/mobile/bootstrap` 로 현재 brand 존재 여부와 `onboarding_completed` 상태를 본다.
- brand 가 없으면 Stitch 온보딩 화면(`welcome` → `1.` → `2.` → `3.`)으로 이동한다.
- 온보딩 2단계의 `분석하기`는 `POST /api/mobile/onboarding/complete` 를 호출한다.
- 동일 입력이고 새 로고/새 참고 이미지가 없으면 서버는 `status="existing"` 으로 기존 분석 결과를 그대로 돌려줄 수 있다.
- 입력값이나 참고 자산이 달라지면 서버는 같은 엔드포인트에서 브랜드를 재분석하고, 신규면 `create`, 기존이면 `update_profile` 로 반영한다.

### 1.3 실행 플로우

```text
사용자가 모바일 온보딩 진행
  │
  ├─ 브랜드 이름 / 대표 색상 / 분위기 / 설명 / 로고 입력
  ├─ 참고 이미지 최대 4장 업로드
  ├─ (선택) Instagram URL 입력
  │
  └─ POST /api/mobile/onboarding/complete
       │
       ├─ 로고 결정
       │    1) 새 로고 업로드 → brand_assets 저장
       │    2) 기존 brand.logo_path 존재 → 기존 로고 재사용
       │    3) 둘 다 없으면 → 워드마크 PNG 자동 생성
       │
       ├─ 참고 이미지 저장
       ├─ Instagram URL 있으면
       │    Mac 캡처 워커 우선 → 실패 시 VM fallback 캡처
       │
       ├─ 분석 이미지가 있고 API 준비됨
       │    → GPT Vision 분석으로 style_prompt 생성
       │
       ├─ 분석 이미지가 없거나 API 미준비
       │    → 구조화 입력을 합친 텍스트 기반 content 사용
       │
       └─ BrandService.create(...) 또는 update_profile(...)
            → brand 생성/제한적 갱신
```

### 1.4 프롬프트 흐름

#### `build_vision_analysis_prompt(user_freetext)` 구조
정의: [services/onboarding_service.py:33](../services/onboarding_service.py#L33)

블록:
1. **업종 고정** — 카페·베이커리·디저트 외 다른 업종 이미지가 와도 톤만 참고, 카테고리는 고정.
2. **브랜드 시각 자산 연출 방침** — "머그컵·접시·포장·냅킨·간판에 로고/이름을 각인" 을 **강제 규칙** 으로 명시. 이 한 줄이 이후 모든 이미지 생성 프롬프트에 자연 전파되게 하려는 장치.
3. **사용자 자유 텍스트** — `_merge_structured_inputs_into_freetext()` 결과를 그대로 삽입.
4. **작업 단계** — ① 객관 관찰 → ② 카테고리 단서 추출 → ③ 업종 확정 → ④ 정제된 브랜드 설명 작성.
5. **출력 형식** — 자연스러운 한국어 문단. 마크다운 제목·번호 목록 금지. 첫 문장에 업종 명시 필수.

#### `_merge_structured_inputs_into_freetext()`
[services/onboarding_service.py:271](../services/onboarding_service.py#L271). 사용자 입력(이름·색상·분위기) 을 프리픽스로 붙여 자유 텍스트 앞단에 삽입 — GPT 가 구조화 힌트를 먼저 읽도록.

#### Vision API 호출 페이로드
[services/onboarding_service.py:160](../services/onboarding_service.py#L160) `GPTVisionAnalyzer.analyze()`:

```python
client.chat.completions.create(
    name="onboarding.vision_brand_style",   # Langfuse observation 이름
    model=settings.TEXT_MODEL,               # 예: gpt-5-mini
    messages=[{
        "role": "user",
        "content": [
            {"type": "text", "text": system_prompt},
            {"type": "image_url", "image_url": {"url": "data:image/png;base64,..."}},
            ...  # 캡처된 모든 이미지
        ],
    }],
    timeout=settings.TEXT_TIMEOUT,
)
```

반환 문자열이 곧 `BrandDraft.style_prompt` → 사용자 검수 후 `brands.style_prompt` 컬럼에 저장 → 이후 모든 생성 요청의 `brand_prompt` 로 전파.

### 1.5 데이터 구조

#### `BrandDraft` (메모리 전용)
[services/onboarding_service.py:109](../services/onboarding_service.py#L109)

| 필드 | 비고 |
|------|------|
| `name` / `color_hex` / `logo_path` | 사용자 입력 또는 자동 생성/기존 재사용 결과 |
| `input_instagram_url` / `input_description` / `input_mood` | 추적성 보장 — 분석 소스 박제 |
| `style_prompt` | GPT 분석 결과. 검수 단계에서 `with_edited_style_prompt()` 로만 수정 |

`frozen=True` 불변 dataclass.

#### `brands` 테이블
[models/brand.py](../models/brand.py). 6개 분할 영역:
- PK: `id` (UUID)
- 인스타 연결 (온보딩 시 NULL): `instagram_account_id UNIQUE nullable`, `instagram_username`
- 아이덴티티: `name`, `color_hex`, `logo_path`
- 스타일 입력: `input_instagram_url`, `input_description`, `input_mood`
- 스타일 결과: `style_prompt`
- 메타: `created_at` (현재도 `updated_at` 은 없음. 같은 row 를 갱신하지만 변경 이력 컬럼은 아직 없다)

### 1.6 세션 키

| 키 | 설정 시점 | 용도 |
|---|---|---|
| `onboarding_brand_name` / `_color` / `_mood` / `_logo` | 입력 위젯 | 입력 상태 |
| `onboarding_description` / `_instagram_url` | 입력 위젯 | 입력 상태 |
| `onboarding_draft` | 분석 완료 시 | 검수 단계 분기 |
| `onboarding_edit_mode` | "수정" 클릭 | 검수/편집 토글 |
| `onboarding_edited_style_prompt` | 편집 textarea | 편집 중 버퍼 |
| `onboarding_done` | 확정 시 | 저장 성공 마커 (현재 미사용, 향후 분기용) |
| `_current_brand` | 확정 후 로드 시 | 생성 플로우에서 `brand_id` FK 로 사용 |
| `brand_prompt` | 확정 후 로드 시 | 생성 프롬프트의 "[[브랜드 가이드라인]]" 섹션 |

### 1.7 외부 의존성

| 의존성 | 호출부 | 비고 |
|--------|--------|------|
| `browser-use` CLI | [backends/insta_capture.py:150](../backends/insta_capture.py#L150) | subprocess. 미설치면 `RuntimeError`. |
| OpenAI Vision API | [services/onboarding_service.py:160](../services/onboarding_service.py#L160) | 모델: `settings.TEXT_MODEL`. Langfuse `name="onboarding.vision_brand_style"`. |
| Langfuse Cloud | `langfuse.openai` wrapper | 자동 trace. 키 미설정 시 no-op. |

### 1.8 에러 처리

| 단계 | 케이스 | 현재 동작 |
|------|--------|-----------|
| 캡처 | browser-use 실패 | `CalledProcessError` → `RuntimeError` 감싸 전파. 이미지 누락 시 `logger.warning` 후 진행. |
| Vision | 타임아웃·인증 실패 | OpenAI 예외 그대로 전파 → `_render_input_stage` 의 except 에서 `st.error` + `st.exception` expander 로 traceback 노출. |
| 저장 | 동일 `instagram_account_id` 의 다른 brand 존재 | `link_instagram` 시점에 `BrandAlreadyExistsError`. 온보딩 자체엔 영향 없음 (연결 단계에서만). |

에러 발생 시 `onboarding_draft` 는 None 으로 남아서 재시도가 가능. 다만 유효한 draft 생성 직후 DB 저장 실패면 사용자가 "이대로 확정"을 다시 누르면 됨 (`create` 는 idempotent 아님, 중복이면 unique 제약으로 실패 — 현재 `instagram_account_id` NULL 이라 문제 없음).

### 1.9 후속 활용

저장된 `brands.style_prompt` 는 **모든 생성의 공통 프롬프트**:
- 텍스트: [utils/prompt_builder.py:75](../utils/prompt_builder.py#L75) `build_text_prompt` 의 "[[브랜드 가이드라인]]" 섹션
- 이미지: [utils/prompt_builder.py:184](../utils/prompt_builder.py#L184) `build_image_prompt` 의 `Brand guidelines (MUST follow):` 섹션
- 캡션: [services/caption_service.py](../services/caption_service.py) system prompt 의 `brand_prompt`

자세한 조립 로직은 [generation.md](generation.md) 참고.

---

## 2. 인스타 OAuth 연결

### 2.0 현재 모바일 PWA 기준 요약

모바일 업로드는 OAuth 연결된 계정만 사용한다.

- `.env`의 `META_ACCESS_TOKEN` / `INSTAGRAM_ACCOUNT_ID` fallback은 모바일 업로드에서 사용하지 않는다.
- 업로드 전에 `brands.instagram_account_id`와 활성 `instagram_connections` row가 필요하다.
- 연결이 없거나 토큰이 만료되면 업로드 API는 `409`와 “인스타그램 계정을 먼저 연결” 메시지를 반환한다.
- 수동 연결 UI는 숫자 Instagram business account ID가 아니라 `@username`을 입력받는다.
- 입력한 `@username`은 현재 Meta 로그인 계정이 접근 가능한 Facebook Page 후보 목록 안에서만 매칭된다.

이 아래 Streamlit `app.py` 사이드바 설명은 legacy 참고용이다.

### 2.1 개요

Meta Graph API v19.0 로 사용자 IG Business 계정 연결 후, 60일 long-lived 토큰을 **Fernet 대칭키로 암호화**해 `instagram_connections` 에 저장. `brands.instagram_account_id / _username` 은 `link_instagram()` 을 통해 한 번 채워진다.

원칙 상:
- `brands` 는 불변 → 가변 데이터(토큰/만료/활성상태) 는 `instagram_connections` 로 격리
- 1 브랜드 : 1 연결 → `UNIQUE(brand_id)`
- 해제는 `is_active=False` soft delete

### 2.2 진입점과 세션 키

- 진입: [app.py:216](../app.py#L216) `render_instagram_connection(settings, brand=_loaded_brand)` — 사이드바 위젯.
- 렌더 가드: [ui/instagram_connect.py:27-32](../ui/instagram_connect.py#L27-L32) `brand is None` 또는 `META_APP_ID`/`META_APP_SECRET` 미설정 시 no-op.

세션 키:
| 키 | 의미 |
|---|---|
| `oauth_state` | `uuid4()` 로 발급한 CSRF 토큰 |
| `ig_connecting` | 콜백 처리 중 플래그 (연속 요청 방지) |
| `pending_ig_token` | 자동 조회 실패 후 수동 입력 대기용 `(long_token, expires_in)` |

### 2.3 실행 플로우

```
사이드바 렌더
  └─ ui/instagram_connect.py:17  render_instagram_connection(settings, brand)
        │
        ├─ [초기]  "🔗 자동 연결하기" 클릭
        │    └─ state = uuid4()
        │    └─ auth_svc.generate_oauth_url(state)
        │         Meta OAuth URL 빌드:
        │           client_id / redirect_uri / state
        │           scope = instagram_basic, instagram_content_publish,
        │                   pages_show_list, pages_read_engagement
        │    → 브라우저 리다이렉트 (meta refresh)
        │
        ├─ [Meta 로그인 완료 후 콜백]  ?code=...&state=...
        │    │
        │    ├─ CSRF 검증: received_state == expected_state
        │    │
        │    ├─ auth_svc.exchange_code_for_token(code)          → short_token
        │    │    services/instagram_auth_service.py:55
        │    │    GET /v19.0/oauth/access_token
        │    │
        │    ├─ auth_svc.exchange_for_long_lived_token(short)   → (long_token, expires_in=60일)
        │    │    services/instagram_auth_service.py:79
        │    │    GET /v19.0/oauth/access_token?grant_type=fb_exchange_token
        │    │
        │    ├─ auth_svc.fetch_instagram_account(long_token)
        │    │    services/instagram_auth_service.py:99
        │    │    ①  GET /me/accounts?fields=...,instagram_business_account
        │    │    ②  GET /{ig_account_id}?fields=username
        │    │    → { instagram_account_id, instagram_username,
        │    │       facebook_page_id, facebook_page_name }
        │    │
        │    │   [성공]
        │    ├─ auth_svc.save_connection(brand.id, long_token, expires_in, ig_info)
        │    │    services/instagram_auth_service.py:199
        │    │    ①  BrandService.link_instagram()
        │    │         brands.instagram_account_id / _username 1회 채움
        │    │         (다른 brand 가 소유 중이면 BrandAlreadyExistsError)
        │    │    ②  InstagramConnection UPSERT
        │    │         access_token = encrypt_token(..., TOKEN_ENCRYPTION_KEY)
        │    │         token_expires_at = now + expires_in
        │    │         is_active = True
        │    │
        │    │   [자동 조회 실패]  ValueError
        │    └─ session_state.pending_ig_token = (long_token, expires_in)
        │         → 수동 입력 모드 expander 오픈
        │
        ├─ [수동 입력]  expander "🛠️ 수동으로 ID 입력하여 연결"
        │    └─ auth_svc.fetch_instagram_account_manually(token, manual_id)
        │         services/instagram_auth_service.py:176
        │         GET /v19.0/{instagram_id}?fields=username,id,name
        │    └─ save_connection(...)
        │    → del session_state.pending_ig_token
        │
        ├─ [이미 연결됨]  connection.is_active == True
        │    └─ ✅ @{brand.instagram_username} 연결됨
        │    └─ [🔄 재연결]  → generate_oauth_url 다시
        │    └─ [❌ 해제]   → revoke_connection(brand.id)
        │                      is_active = False  (soft delete)
        │
        └─ get_connection(brand.id) 로 현재 상태 조회 후 분기
             services/instagram_auth_service.py:255
```

### 2.4 토큰 저장과 업로드 시 주입

#### 저장 (암호화)
[services/instagram_auth_service.py:211](../services/instagram_auth_service.py#L211):
```python
encrypted_token = encrypt_token(access_token, settings.TOKEN_ENCRYPTION_KEY)
```
`utils/crypto.py` 의 Fernet 대칭키. `TOKEN_ENCRYPTION_KEY` 는 `.env` 에 base64 urlsafe 32바이트.

#### 게시 시점 주입
[services/instagram_auth_adapter.py:18](../services/instagram_auth_adapter.py#L18) `apply_user_token(settings, brand)`:

```
brand is None                        → False (온보딩 필요)
brand.instagram_account_id is None   → .env 의 META_ACCESS_TOKEN 폴백
conn 없음 / is_active=False           → 폴백
정상 경로:
  decrypted = decrypt_token(conn.access_token, TOKEN_ENCRYPTION_KEY)
  settings.META_ACCESS_TOKEN   = decrypted       ← 런타임 주입
  settings.INSTAGRAM_ACCOUNT_ID = brand.instagram_account_id
  return True
```

복호화 실패(TOKEN_ENCRYPTION_KEY 불일치 등) 는 `RuntimeError` 로 **예외 전파** — silent False 금지 (CP7 에서 변경). 이유를 사용자가 보게 하기 위함.

### 2.5 데이터 구조

#### `instagram_connections` 테이블
[models/instagram_connection.py](../models/instagram_connection.py). 가변 엔티티라 `TimestampMixin` 사용 (`updated_at` 있음).

| 필드 | 비고 |
|------|------|
| `id` UUID PK | |
| `brand_id` FK → brands.id | **UNIQUE** (1:1) |
| `access_token` | Fernet 암호문 |
| `token_type` | `"long_lived"` |
| `token_expires_at` | UTC, 보통 now+60일 |
| `facebook_page_id` / `facebook_page_name` | 자동 조회 시 채움. 수동 연결이면 `"수동 연결"` |
| `is_active` | 해제 시 False (soft delete) |
| `created_at` / `updated_at` | |

### 2.6 외부 의존성

| 의존성 | 버전 | 호출부 |
|--------|------|--------|
| Meta Graph API | **v19.0** | [services/instagram_auth_service.py:26](../services/instagram_auth_service.py#L26) `BASE_URL` 상수 |
| `httpx.AsyncClient` | — | OAuth / 계정 조회 전체 |
| `cryptography.fernet` | — | `utils/crypto.py` |

### 2.7 에러 처리

| 케이스 | 위치 | 동작 |
|--------|------|------|
| CSRF state 불일치 | [ui/instagram_connect.py:48](../ui/instagram_connect.py#L48) | warning + `query_params.clear()` |
| short→long 교환 실패 | [services/instagram_auth_service.py:86](../services/instagram_auth_service.py#L86) | `raise_for_status()` → 상위 except |
| Facebook 페이지 없음 / IG 계정 미연결 | [services/instagram_auth_service.py:136-140](../services/instagram_auth_service.py#L136-L140) | ValueError → UI 에서 **수동 입력 모드로 전환** |
| 여러 IG 계정 발견 | [services/instagram_auth_service.py:142-147](../services/instagram_auth_service.py#L142-L147) | warning 로그 + 첫 번째 선택 (MVP) |
| username 누락 | [services/instagram_auth_service.py:161-166](../services/instagram_auth_service.py#L161-L166) | ValueError |
| 수동 입력 ID 무효 | [services/instagram_auth_service.py:182](../services/instagram_auth_service.py#L182) | ValueError → st.error |
| 중복 연결 시도 | [services/instagram_auth_service.py:226](../services/instagram_auth_service.py#L226) | 기존 레코드 UPDATE (UPSERT) |
| 토큰 복호화 실패 | [services/instagram_auth_adapter.py:45](../services/instagram_auth_adapter.py#L45) | `RuntimeError("TOKEN_ENCRYPTION_KEY 확인")` 전파 |
| 해제 | [ui/instagram_connect.py:110](../ui/instagram_connect.py#L110) | `is_active=False` — 레코드는 유지 |

모든 예외는 `logger.exception` 으로 스택 트레이스 콘솔에 남고, UI 는 `st.error` + 필요시 `st.exception` expander 로 노출 (CP7).

### 2.8 비교: 온보딩 vs 연결의 설계 차이

| 관점 | `brands` (온보딩) | `instagram_connections` (연결) |
|------|-------------------|-------------------------------|
| 불변/가변 | 불변 (updated_at 없음) | 가변 (TimestampMixin) |
| 재시도 | 1회성 (중복 create 불가) | 재연결 허용 (UPSERT + is_active toggle) |
| 삭제 | 물리 삭제 | soft delete (`is_active=False`) |
| 식별자 | `id` UUID + `instagram_account_id` UNIQUE | `brand_id` UNIQUE |
| 외부 의존 | OpenAI Vision + browser-use | Meta Graph API v19.0 + Fernet |

스타일(브랜드) 과 연결(토큰) 을 **서로 다른 수명 주기** 로 두는 게 핵심 설계 의도. 토큰이 만료·재발급되어도 브랜드 정체성은 불변으로 유지.
