# 프로젝트 아키텍처 (Architecture)

> **프로젝트:** 생성형 AI 기반 광고 콘텐츠 제작 서비스 (MVP)  
> **최종 수정일:** 2026-04-02

---

## 1. 시스템 아키텍처 개요

PRD 5.1에서 정의한 전체 흐름을 구체화한 아키텍처입니다.

```
┌─────────────────────────────────────────────────────┐
│                      User                            │
│               (소상공인 · 웹 브라우저)                   │
└─────────────────┬───────────────────────────────────┘
                  │ HTTP (localhost:8501)
                  ▼
┌─────────────────────────────────────────────────────┐
│              Streamlit UI (app.py)                    │
│  ┌───────────────────┐   ┌────────────────────────┐  │
│  │    입력 영역        │   │     출력 영역            │  │
│  │  · 상품명           │   │  · 광고 문구 (3개)       │  │
│  │  · 상품 설명        │   │  · 홍보 문장 (2개)       │  │
│  │  · 스타일 선택      │   │  · 광고 이미지           │  │
│  │  · 생성 타입 선택   │   │  · 다운로드 버튼          │  │
│  └───────────────────┘   └────────────────────────┘  │
├─────────────────────────────────────────────────────┤
│              Controller Logic (app.py)                │
│         · 이벤트 핸들링 · 서비스 호출 · 에러 처리         │
└─────────────────┬───────────────────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────────────────┐
│                Service Layer                         │
│  ┌──────────────────────┐  ┌──────────────────────┐  │
│  │   TextService         │  │   ImageService        │  │
│  │  · generate_copy()    │  │  · generate_image()   │  │
│  │  · Mock / API 전환    │  │  · Mock / API 전환     │  │
│  └──────────┬───────────┘  └──────────┬───────────┘  │
└─────────────┼──────────────────────────┼────────────┘
              │                          │
              ▼                          ▼
┌──────────────────────┐  ┌──────────────────────────┐
│  PromptBuilder       │  │   AI Model API / Mock     │
│  (utils/)            │  │  · OpenAI GPT             │
│  · build_text_prompt │  │  · Hugging Face API       │
│  · build_image_prompt│  │  · Mock 응답 (개발용)       │
└──────────────────────┘  └──────────────────────────┘
```

---

## 2. 디렉토리 구조

PRD 5.2를 기반으로 확장한 프로젝트 구조입니다.

```
Gen_for_SmallBusiness/
│
├── app.py                      # 메인 엔트리포인트 (Streamlit)
│
├── services/                   # 서비스 레이어 (비즈니스 로직)
│   ├── __init__.py
│   ├── text_service.py         # 광고 문구 생성 서비스
│   ├── image_service.py        # 광고 이미지 생성 서비스
│   ├── caption_service.py      # 인스타 캡션·해시태그 생성
│   ├── instagram_service.py    # Meta Graph API 인스타 업로드
│   └── history_service.py      # 비동기 DB 저장·조회
│
├── utils/                      # 유틸리티
│   ├── __init__.py
│   └── prompt_builder.py       # 프롬프트 생성 함수
│
├── config/                     # 설정
│   ├── __init__.py
│   ├── database.py             # SQLAlchemy 비동기 엔진 및 세션 설정
│   └── settings.py             # 환경 변수 로드 (pydantic-settings)
│
├── models/                     # SQLAlchemy ORM 모델
│   ├── __init__.py
│   ├── base.py                 # TimestampMixin 등 기본 베이스
│   └── history.py              # 생성 내역 저장 테이블 모델
│
├── schemas/                    # Pydantic 스키마 (입출력 정의)
│   ├── __init__.py
│   ├── text_schema.py          # 텍스트 생성 입출력 스키마
│   ├── image_schema.py         # 이미지 생성 입출력 스키마
│   └── history_schema.py       # 히스토리 데이터 교환 스키마
│
├── docs/                       # 프로젝트 문서
│   ├── PRD.md                  # 기획서
│   ├── stack.md                # 기술 스택
│   └── architecture.md         # 아키텍처 (이 문서)
│
├── .env                        # 환경 변수 (Git 제외)
├── .env.example                # 환경 변수 템플릿
├── .gitignore
├── requirements.txt            # Python 의존성
└── README.md                   # 프로젝트 소개
```

---

## 3. 레이어 구조 및 역할

### 3.1 레이어 다이어그램

```
┌─────────────┐
│  Streamlit   │  ← UI 레이어: 사용자 입력/출력만 담당
│  (app.py)    │
├─────────────┤
│  Service     │  ← 서비스 레이어: 비즈니스 로직 담당
│  Layer       │     Mock / API 전환 로직 포함
├─────────────┤
│  Utils       │  ← 유틸 레이어: 프롬프트 생성, 공통 함수
├─────────────┤
│  Config      │  ← 설정 레이어: 환경 변수, 모델 설정
├─────────────┤
│  Schemas     │  ← 스키마 레이어: 입출력 데이터 정의
└─────────────┘
```

### 3.2 각 레이어 역할

| 레이어 | 파일 | 역할 | 규칙 |
|--------|------|------|------|
| **UI** | `app.py` | Streamlit 위젯 배치, 이벤트 처리, 결과 표시 | 비즈니스 로직 금지, Service 호출만 |
| **Service** | `services/*.py` | AI API 호출, DB 삽입/조회 로직 | 모든 비즈니스 로직 집중 |
| **Model** | `models/*.py` | SQLAlchemy ORM 기반 테이블 매핑 | 상태, 관계형 구조 정의 |
| **Utils** | `utils/*.py` | 프롬프트 조립, 공통 유틸리티 | 순수 함수, 상태 없음 |
| **Config** | `config/*.py` | 환경 변수, DB 엔진 및 세션 팩토리 | pydantic-settings 및 AsyncSession |
| **Schemas** | `schemas/*.py` | Pydantic 모델로 입출력 및 페이로드 정의 | 데이터 정의만, 제어 로직 없음 |

---

## 4. 핵심 컴포넌트 상세

### 4.1 `app.py` — 메인 엔트리포인트

```python
# 역할:
# - Streamlit 페이지 구성 (한 페이지)
# - 입력 폼 렌더링
# - 생성 버튼 이벤트 → Service 호출
# - 결과 표시 (문구 / 이미지)
# - 에러 처리 및 로딩 상태 표시

# 주요 흐름:
# 1. 사용자가 상품 정보 입력
# 2. 생성 타입 선택 (문구 / 이미지)
# 3. "생성" 버튼 클릭
# 4. Service 호출 → 결과 반환
# 5. 결과를 UI에 표시
```

### 4.2 `services/text_service.py` — 광고 문구 및 전략 생성

```python
# 역할:
# - 마케팅 목적(goal)에 따른 광고 문구 생성 비즈니스 로직
# - 업로드 이미지 존재 시 시각적 특징을 텍스트 힌트(image_hint)로 변환 전송
# - PromptBuilder로 전략적 프롬프트 생성 → OpenAI API 호출

# 주요 메서드:
# - generate_ad_copy(request: TextGenerationRequest) -> TextGenerationResponse
#   → [광고 문구] 3개 + [홍보 문장] 2개 + [스토리 카피] 3개 반환
```

### 4.3 `services/image_service.py` — 광고 비주얼 생성 및 합성

```python
# 역할:
# - 광고/홍보 이미지 생성 및 스토리용 텍스트 합성 비즈니스 로직
# - API 모드: HF 추론 API 호출 (업로드 이미지 레퍼런스 준수 가이드 포함)
# - 스토리 생성: 생성된 9:16 이미지 위에 Pillow를 이용해 텍스트 오버레이 합성

# 주요 메서드:
# - generate_ad_image(request: ImageGenerationRequest) -> ImageGenerationResponse
# - compose_story_image(image_bytes, text, style) -> bytes (Pillow 기반 9:16 합성)
```

### 4.4 `services/instagram_service.py` — 인스타그램 업로드

```python
# 역할:
# - 생성된 이미지+캡션을 인스타그램 비즈니스 계정에 자동 포스팅
# - Mock 모드: 가짜 업로드 시뮬레이션
# - Real 모드: JPEG 변환 → FreeImage 호스팅 → Meta Graph API 게시

# 주요 메서드:
# - upload_mock(image_bytes, caption) → Generator (상태 메시지 yield, 마지막 "DONE")
# - upload_real(image_bytes, caption) → Generator (JPEG 변환 → 호스팅 → 컨테이너 → 발행)

# 핵심 흐름:
# 1. PIL로 WebP/PNG → JPEG 강제 변환
# 2. FreeImage.host API에 base64 업로드 → public URL 획득
# 3. Meta Graph API /{ig_id}/media 에 image_url+caption 전달 → container ID
# 4. Meta Graph API /{ig_id}/media_publish 에 container ID 전달 → 피드 게시 완료
```

### 4.5 `utils/prompt_builder.py` — 전략적 프롬프트 생성

```python
# 역할:
# - 마케팅 목적(Goal)을 최우선 전략으로 하는 프롬프트 조립
# - 업로드 이미지 레퍼런스 및 출력 안정성 가이드 포함

# 주요 함수:
# - build_text_prompt(product_name, description, style, goal, image_hint)
# - build_image_prompt(product_name, description, style, goal, ad_copy, has_reference)
```

### 4.6 `config/settings.py` — 환경 설정

```python
# 역할:
# - .env 파일에서 환경 변수 로드
# - 타입 안전한 설정값 제공

# 주요 설정:
# - OPENAI_API_KEY: str
# - HUGGINGFACE_API_KEY: str
# - USE_MOCK: bool (Mock/API 전환)
# - TEXT_MODEL: str (기본값: gpt-5-mini)
# - IMAGE_MODEL: str (기본값: black-forest-labs/FLUX.1-schnell)
```

---

## 5. 데이터 흐름

PRD 7장에서 정의한 데이터 흐름의 상세 구현입니다.

### 5.1 광고 문구 생성 흐름

```
사용자 입력
  │  상품명: "수제 마카롱"
  │  설명: "프랑스산 버터 사용"
  │  홍보 목적: "신상품 홍보" [NEW]
  │  스타일: "감성"
  │  (업로드 이미지 있을 시 image_hint 생성) [NEW]
  ▼
[app.py] TextGenerationRequest 생성 (goal, image_data 포함)
  │
  ▼
[text_service.py] generate_ad_copy()
  │
  ├── USE_MOCK=true ──→ Mock 응답 반환
  │
  └── USE_MOCK=false
        │
        ▼
      [prompt_builder.py] build_text_prompt()
        │  → 마케팅 목적에 따른 페르소나 및 글 톤 전략 수립
        ▼
      [OpenAI GPT API] → 응답 수신
        │
        ▼
      TextGenerationResponse
        │  · ad_copies: 피드용 짧은 카피 3개
        │  · promo_sentences: SNS 상세 설명 2개
        │  · story_copies: 스토리용 훅 3개 [NEW]
        ▼
[app.py] 결과 표시 및 인스타 피드/스토리 상세 UI 활성화
```

### 5.2 광고 이미지 생성 흐름

```
사용자 입력
  │  광고 문구 및 홍보 목적
  │  스타일: "고급"
  │  (업로드 이미지 레퍼런스 존재 시 has_reference=True) [NEW]
  ▼
[app.py] ImageGenerationRequest 생성 (goal, image_data 포함)
  │
  ▼
[image_service.py] generate_ad_image()
  │
  ├── USE_MOCK=true ──→ 플레이스홀더 이미지 반환
  │
  └── USE_MOCK=false
        │
        ▼
      [prompt_builder.py] build_image_prompt()
        │  → 홍보 목적에 따른 이미지 구도/소품 전략 생성
        ▼
      [GPT (gpt-5-mini)] → 영문 프롬프트 최적화 번역
        │
        ▼
      [Hugging Face Inference API] → 이미지 생성
        │
        ▼
      ImageGenerationResponse
        │  · image_data: bytes (1:1 또는 9:16 배경)
        ▼
[app.py] 결과 이미지 표시 및 [스토리용 합성] 버튼 노출
```

### 5.3 인스타그램 업로드 흐름

```
사용자가 "내 인스타그램에 바로 올리기" 버튼 클릭
  │  image_bytes: 생성된 이미지 바이너리
  │  caption: 편집된 캡션 + 해시태그
  ▼
[app.py] InstagramService 호출
  │
  ├── USE_MOCK=true ──→ Mock 업로드 시뮬레이션 (1.5초 대기 → DONE)
  │
  └── USE_MOCK=false
        │
        ▼
      [instagram_service.py] upload_real()
        │  1) PIL Image 로 열어서 JPEG 강제 변환
        │  2) FreeImage.host API 에 base64 업로드
        │     → public_image_url 획득 (https://iili.io/...)
        ▼
      [Meta Graph API] /{ig_id}/media
        │  image_url + caption + access_token 전송
        │  → container creation_id 수신
        ▼
      [Meta Graph API] /{ig_id}/media_publish
        │  creation_id 전송
        │  → 인스타그램 피드에 게시물 발행 완료
        ▼
      yield "DONE" → [app.py] st.success() + st.balloons()
```

---

## 6. Mock ↔ API 전환 전략

PRD 개발 원칙 **"Mock → 실제 API 연동 순서로 개발"** 을 아키텍처에 반영합니다.

```python
# services/text_service.py 예시 구조

class TextService:
    def __init__(self, settings: Settings):
        self.settings = settings

    async def generate_ad_copy(
        self, request: TextGenerationRequest
    ) -> TextGenerationResponse:
        if self.settings.USE_MOCK:
            return self._mock_response(request)
        return await self._api_response(request)

    def _mock_response(self, request) -> TextGenerationResponse:
        # 하드코딩된 테스트 응답
        ...

    async def _api_response(self, request) -> TextGenerationResponse:
        # OpenAI API 호출
        ...
```

### 전환 방법
- `.env` 파일의 `USE_MOCK=true` → `USE_MOCK=false` 변경만으로 전환
- 코드 수정 없이 환경 변수로 제어

---

## 7. Pydantic 스키마 설계

### 7.1 텍스트 생성 스키마

```python
# schemas/text_schema.py

class TextGenerationRequest(BaseModel):
    product_name: str           # 상품명 (필수)
    description: str = ""       # 상품 설명
    style: str = "기본"          # 광고 스타일
    goal: str = "일반 홍보"       # [NEW] 홍보 목적
    image_data: bytes | None    # [NEW] 업로드 원본 이미지

class TextGenerationResponse(BaseModel):
    ad_copies: list[str]        # 광고 문구 3개
    promo_sentences: list[str]  # 홍보 문장 2개
    story_copies: list[str]     # [NEW] 스토리 훅 3개
```

### 7.2 이미지 생성 스키마

```python
# schemas/image_schema.py

class ImageGenerationRequest(BaseModel):
    prompt: str                 # 광고 문구 또는 설명
    product_name: str           # [NEW] 상품명
    description: str            # [NEW] 상품 설명
    goal: str                   # [NEW] 홍보 목적
    style: str = "기본"          # 스타일 옵션
    image_data: bytes | None    # [NEW] 레퍼런스 이미지

class ImageGenerationResponse(BaseModel):
    image_data: bytes           # 생성된 바이터리
    revised_prompt: str = ""    # 최적화된 영문 프롬프트
```

---

## 8. 에러 처리 전략

PRD 3.3 UX 요구사항 **"에러 처리"** 에 대한 구현 방침입니다.

| 에러 유형 | 처리 방식 | UI 표현 |
|----------|----------|---------|
| API 키 미설정 | 앱 시작 시 검증 | `st.error("API 키를 설정해주세요")` |
| API 호출 실패 | try/except, 재시도 안내 | `st.error("생성에 실패했습니다. 다시 시도해주세요")` |
| 입력값 누락 | Pydantic 검증 | `st.warning("상품명을 입력해주세요")` |
| 응답 시간 초과 | timeout 설정 | `st.error("응답 시간이 초과되었습니다")` |
| Mock 모드 알림 | 설정 확인 | `st.info("현재 테스트 모드로 실행 중입니다")` |

---

## 9. Phase별 아키텍처 진화

| Phase | 아키텍처 상태 | 활성 컴포넌트 |
|-------|-------------|-------------|
| **Phase 1** | 빈 구조 생성 | `app.py` (Hello World), `requirements.txt` |
| **Phase 2** | UI 완성 | `app.py` (입력 폼 + 출력 영역) |
| **Phase 3** | 문구 생성 연결 | + `text_service.py`, `prompt_builder.py`, `schemas/` |
| **Phase 4** | 이미지 생성 연결 | + `image_service.py` |
| **Phase 5** | 통합 완성 | 전체 컴포넌트 + 에러 처리 + UX 개선 |
| **Phase 6** | DB 아카이브 | + `history_service.py`, `models/`, `config/database.py` |
| **Phase 7** | 인스타 연동 | + `instagram_service.py`, `caption_service.py`, Meta Graph API |

---

## 10. 향후 확장 아키텍처 (Post-MVP)

PRD 11장의 향후 확장 방향에 대비한 아키텍처 확장 포인트입니다.

```
현재 (MVP + Phase 7)                향후 확장
─────────────────────────────────────────────────────
Streamlit UI                  →    다중 페이지 라우팅 분리
단일 app.py 멀티 탭            →    pages/ 디렉토리 구조
데이터베이스 (SQLite)          →    PostgreSQL 등 외부 DB 스케일업
환경 변수 설정만               →    + 사용자 인증 및 멀티 테넌트 (로그인)
인스타그램 즉시 업로드         →    + 예약 업로드 (날짜/시간 지정)
Meta Graph API 단일 SNS       →    + 네이버 블로그, 카카오 채널 다중 SNS
─ (없음)                      →    + 광고 성과 분석 대시보드
```
