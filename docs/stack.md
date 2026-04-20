# 기술 스택 (Technology Stack)

> Legacy note: 이 문서는 초기 Streamlit MVP 기술 스택이다.
> 현재 운영 기준은 `mobile_app.py + Stitch PWA`, FastAPI, Caddy, SQLite `/srv/brewgram/data`, 선택적 `worker_api.py`, 선택적 Mac 캡처 워커를 포함한다.

> **프로젝트:** 생성형 AI 기반 광고 콘텐츠 제작 서비스 (MVP)  
> **최종 수정일:** 2026-04-02

---

## 1. 기술 스택 전체 맵

```
┌──────────────────────────────────────────────┐
│               Streamlit UI                    │
│          (단일 페이지 웹 인터페이스)              │
├──────────────────────────────────────────────┤
│           Controller (app.py)                 │
│       (이벤트 핸들링 · 흐름 제어)                │
├──────────────────────────────────────────────┤
│             Service Layer                     │
│   ┌──────────────┐  ┌───────────────────┐    │
│   │ TextService   │  │  ImageService     │    │
│   │ (광고 문구)    │  │  (광고 이미지)      │    │
│   └──────────────┘  └───────────────────┘    │
│   ┌────────────────────────────────────┐    │
│   │ InstagramService (인스타 업로드) [NEW]  │    │
│   └────────────────────────────────────┘    │
├──────────────────────────────────────────────┤
│              Utils / Config                   │
│   ┌──────────────┐  ┌───────────────────┐    │
│   │PromptBuilder │  │  Settings         │    │
│   │(프롬프트 생성) │  │  (환경 설정)       │    │
│   └──────────────┘  └───────────────────┘    │
├──────────────────────────────────────────────┤
│       External APIs / 외부 연동                │
│   (OpenAI GPT · Hugging Face · Meta Graph    │
│    API · FreeImage.host / Mock 응답)            │
└──────────────────────────────────────────────┘
```

---

## 2. 프론트엔드

| 항목 | 기술 | 버전 (권장) | 비고 |
|------|------|------------|------|
| **UI 프레임워크** | Streamlit | `>=1.30` | 한 페이지 구성, Python 단일 언어 |
| **레이아웃** | `st.columns`, `st.tabs` | — | 입력/출력 영역 분리 |
| **입력 위젯** | `st.text_input`, `st.text_area`, `st.selectbox` | — | 상품명 · 설명 · 스타일 · 생성 타입 선택 |
| **출력 위젯** | `st.write`, `st.image`, `st.download_button` | — | 문구 표시 · 이미지 출력 · 다운로드 |
| **상태 관리** | `st.session_state` | — | 생성 결과 세션 유지 |
| **UX 피드백** | `st.spinner`, `st.error`, `st.success` | — | 로딩 표시 · 에러 처리 |

### 선정 근거
- PRD에서 **한 페이지 구성**, **버튼 클릭 → 결과 출력** 구조를 명시
- 1인 개발 MVP → 별도 프론트엔드 프레임워크 불필요
- Python 언어 통일로 러닝 커브 최소화

---

## 3. 백엔드 (Python 단일 애플리케이션)

| 항목 | 기술 | 버전 (권장) | 비고 |
|------|------|------------|------|
| **언어** | Python | `>=3.11` | 타입 힌트 필수 |
| **패키지 관리** | pip + `requirements.txt` | — | PRD에서 명시된 형식 |
| **가상 환경** | venv | — | 프로젝트 의존성 격리 |
| **환경 변수** | python-dotenv | `>=1.0` | `.env` 파일 기반 시크릿 관리 |
| **설정 관리** | pydantic-settings | `>=2.0` | `config/settings.py`에서 환경 변수 로드 |
| **데이터 검증** | Pydantic | `>=2.0` | AI 입출력 및 DB 스키마 정의 |
| **ORM / DB** | SQLAlchemy + aiosqlite | `>=2.0` | 비동기 SQLite 연동 및 쿼리 제어 |

### 선정 근거
- PRD 5.2에서 **`config/settings.py`** 구조를 명시 → pydantic-settings로 구현
- 로그인/DB 없는 MVP → 프레임워크(FastAPI 등) 불필요, Streamlit 직접 연동
- Mock → 실제 API 전환 구조를 위해 서비스 레이어 분리

---

## 4. AI 모델 / API

### 4.1 텍스트 생성 (광고 문구)

| 우선순위 | 기술 | 비고 |
|---------|------|------|
| **Mock** | 하드코딩 응답 | Phase 3 초기 개발용 |
| **1순위** | OpenAI GPT API (`gpt-5-mini`) | 비용 효율적, 한국어 품질 우수 |
| **2순위** | OpenAI GPT API (`gpt-4o`) | 더 높은 품질 필요 시 |

#### 출력 사양 (PRD 3.1 기준)
- 광고 문구 **3개**
- 확장형 홍보 문장 **2개**
- 스타일 반영 · 재생성 지원

### 4.2 비주얼 및 스토리 생성

| 우선순위 | 기술 | 비고 |
|---------|------|------|
| **1순위 (이미지)** | HF Inference API (FLUX.1-schnell) | 1:1 피드용 및 9:16 스토리 배경 생성 |
| **1순위 (합성)** | Pillow (`PIL.ImageDraw`) | 스토리용 이미지 위에 텍스트 오버레이 합성 (9:16 최적화) |
| **폴백** | OpenAI DALL-E 3 API | 높은 품질 필요 시 활용 |

### 선정 근거
- PRD 개발 원칙: **Mock → 실제 API 연동 순서**로 개발
- GPU 미사용 환경 → 외부 API 활용
- **이미지 기획(GPT) → 생성(HF) → 합성(Pillow)** 으로 이어지는 3단계 비주얼 파이프라인 구축

---

## 5. 유틸리티 라이브러리

| 항목 | 기술 | 용도 |
|------|------|------|
| **이미지 합성/편집** | Pillow (`PIL`) | 생성 이미지 JPEG 변환, **스토리용 텍스트 오버레이 합성** |
| **HTTP** | httpx / requests | 외부 API 호출 (OpenAI, HF, Meta, FreeImage) |
| **폰트 처리** | `PIL.ImageFont` | 스토리 합성 시 가독성 높은 한국어 폰트 적용 (macOS/Linux 경로 대응) |

---

## 6. 개발 도구

| 항목 | 기술 | 용도 |
|------|------|------|
| **버전 관리** | Git + GitHub | 소스 코드 관리 |
| **코드 포맷터** | Black | 코드 스타일 통일 |
| **린터** | Ruff | 빠른 Python 린팅 |
| **타입 체크** | mypy (선택) | 정적 타입 분석 |
| **AI 개발 지원** | Claude / Codex | 코드 생성 · 디버깅 |

---

## 7. 배포 옵션

| 우선순위 | 기술 | 비고 |
|---------|------|------|
| **MVP** | 로컬 실행 (`streamlit run app.py`) | PRD 비기능 요구사항: 로컬 실행 가능 |
| **1순위** | Streamlit Community Cloud | 무료 · 즉시 배포 |
| **2순위** | Docker + Cloud Run | 스케일 필요 시 |

---

## 8. 핵심 의존성 (`requirements.txt`)

```txt
# === UI ===
streamlit>=1.30

# === AI ===
openai>=1.0

# === 설정 · 검증 ===
pydantic>=2.0
pydantic-settings>=2.0
python-dotenv>=1.0

# === 속도/비동기 API ===
httpx>=0.25

# === 데이터베이스 ===
sqlalchemy>=2.0
aiosqlite>=0.19

# === 인스타그램 연동 ===
requests>=2.31
Pillow>=10.0
```

---

## 9. 환경 변수 (`.env.example`)

```env
# ── AI API Keys ──
OPENAI_API_KEY=sk-your-openai-api-key-here
HUGGINGFACE_API_KEY=hf_your-huggingface-api-key-here

# ── Application ──
APP_ENV=development       # development | production
LOG_LEVEL=INFO            # DEBUG | INFO | WARNING | ERROR
USE_MOCK=true             # true: Mock 응답 사용 / false: 실제 API 호출

# ── Model Settings ──
TEXT_MODEL=gpt-5-mini                         # 텍스트 생성 모델
IMAGE_MODEL=black-forest-labs/FLUX.1-schnell  # 이미지 생성 모델
IMAGE_SIZE=1024x1024                          # 생성 이미지 크기

# ── Instagram Upload Settings ──
META_ACCESS_TOKEN=EAA...                      # Facebook System User 영구 토큰
INSTAGRAM_ACCOUNT_ID=178...                   # 인스타그램 비즈니스 계정 ID
```

---

## 10. Phase별 기술 활용 매핑

| Phase | 핵심 기술 | 비고 |
|-------|----------|------|
| **Phase 1** — 프로젝트 세팅 | Streamlit, venv, pip | `streamlit run app.py` 실행 확인 |
| **Phase 2** — UI 구현 | Streamlit 위젯, session_state | 입력 폼 · 출력 영역 구성 |
| **Phase 3** — 문구 생성 | PromptBuilder, TextService, Mock → OpenAI GPT | 광고 문구 3개 + 홍보 문장 2개 |
| **Phase 4** — 이미지 생성 | ImageService, Mock → Hugging Face API | 이미지 프롬프트 · 결과 표시 |
| **Phase 5** — 통합·개선 | 에러 처리, 로딩 UX, 코드 정리 | 전체 시나리오 동작 확인 |
| **Phase 6** — 아카이브 | SQLAlchemy, aiosqlite, st.tabs | 히스토리 저장 및 조회 |
| **Phase 7** — 인스타 연동 | InstagramService, Meta Graph API, FreeImage, PIL | 피드 자동 포스팅 |

### 4.3 인스타그램 연동 (Instagram API)

| 역할 | 기술 | 비고 |
|-----|-----|------|
| **이미지 호스팅** | FreeImage.host API | Facebook 크롤러가 정상 접근 가능한 퍼블릭 URL 우회 발급 |
| **포스팅 연동** | Meta Graph API (v19.0) | `/me/media` (컨테이너 생성) 및 `/media_publish` 호출 |
| **권한 관리** | System User Permanent Token | Business Settings를 통한 만료 없는 시스템 사용자 토큰 발급 |
