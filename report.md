# 생성형 AI 기반 소상공인 광고 콘텐츠 제작 서비스: 기술 면접 가이드

이 문서는 프로젝트의 설계 의도, 기술적 선택, 그리고 실제 구현 로직을 코드 근거 기반으로 정리한 기술 백서입니다.

---

## 1. 서비스 개요
- **해결하고자 하는 문제**: 소상공인이 인스타그램 등 SNS 광고를 위해 매번 전문 카피라이터나 디자이너를 고용하기 어렵고, 콘텐츠 제작부터 업로드까지의 과정이 복잡하고 파편화되어 있음.
- **타겟 사용자**: 1인 매장 운영자, 온라인 마켓 초보 사장님.
- **핵심 기능 및 코드 연결**:
    - **광고 문구 생성**: `TextService.generate_ad_copy()`를 통해 상품명과 스타일(감성, 유머 등)에 맞는 카피 3종 및 상세 문장 2종 제공.
    - **광고 이미지 생성**: `ImageService.generate_ad_image()`를 통해 텍스트와 어우러지는 고화질 홍보 이미지 자동 생성.
    - **인스타그램 원클릭 업로드**: `InstagramService.upload_real()`을 통해 생성된 미디어를 Meta Graph API를 거쳐 실제 비즈니스 계정에 게시.

---

## 2. 전체 아키텍처 (코드 기반 설명)

프로젝트는 유지보수성과 확장성을 위해 **Layered Architecture**를 지향하며 각 폴더/파일이 명확한 책임을 가집니다.

- **`app.py` (UI & Controller)**: 
    - Streamlit 프레임워크를 사용하여 사용자 입력을 받고 결과를 렌더링합니다.
    - `st.session_state`를 통해 생성 프로세스의 상태를 관리하고, 각 **Service** 클래스를 호출하는 컨트롤러 역항을 수행합니다.
- **`services/` 레이어 (Business Logic)**:
    - 외부 API(OpenAI, HF, Meta) 통신과 핵심 비즈니스 로직이 담겨 있습니다.
    - 예: `TextService`, `ImageService`, `InstagramService`, `HistoryService`.
- **`utils/prompt_builder.py` (Prompt Engineering)**:
    - AI 모델에 전달될 프롬프트를 템플릿화하여 관리합니다. 비즈니스 로직과 프롬프트 텍스트를 분리하여 프롬프트 품질 개선이 로직에 영향을 주지 않도록 설계되었습니다.
- **`config/` (Configuration)**:
    - `settings.py`: `pydantic-settings`를 활용해 `.env` 환경 변수를 타입 안전하게 로드합니다.
    - `database.py`: SQLAlchemy와 `aiosqlite`를 사용하여 비동기 DB 엔진을 설정합니다.
- **`schemas/` & `models/` (Data Structure)**:
    - `schemas/`: Pydantic 모델을 통해 입출력 데이터를 검증합니다 (`TextGenerationRequest` 등).
    - `models/`: SQLAlchemy ORM 모델로 DB 테이블 구조를 정의합니다 (`History`).

---

## 3. 기술 스택 선택 이유 (코드 기반)

### 3.1 Streamlit (vs FastAPI + React)
- **사용처**: 서비스 전체 UI와 데이터 시각화.
- **이유**: 1인 개발/MVP 단계에서 프론트-백엔드 간의 RESTful API 정의 및 통신 오버헤드를 줄이기 위해 선택했습니다. 
- **대안 미채택 이유**: FastAPI + React는 확장성은 좋으나 초기 개발 공수가 3배 이상 소요되며, 데이터 중심의 단순 인터페이스인 본 프로젝트에는 오버엔지니어링이라 판단했습니다.

### 3.2 SQLite + aiosqlite (vs PostgreSQL)
- **사용처**: `data/history.db` 파일에 홍보물 생성 내역 저장.
- **이유**: 별도의 DB 서버 구축 없이 파일 하나로 로컬 환경에서 즉시 실행 가능합니다. 
- **대안 미채택 이유**: PostgreSQL은 강력하지만 MVP 수준에서는 운영 부담이 큽니다. SQL 표준을 따르는 SQLite로 시작하고, 추후 규모가 커지면 SQLAlchemy 모델은 그대로 유지한 채 `DB_URL`만 변경하여 마이그레이션 가능하도록 설계했습니다.

### 3.3 OpenAI API & Hugging Face Inference API
- **사용처**: `TEXT_MODEL`(gpt-5-mini)로 문구 생성, `IMAGE_MODEL`(SDXL)로 이미지 생성.
- **이유**: 현존하는 가장 강력한 LLM(OpenAI)과 유연한 오픈소스 모델(Hugging Face)의 조합을 통해 비용 대비 높은 퀄리티를 확보했습니다.
- **특이사항**: `image_service.py`에서 GPT를 이용해 한국어 입력을 영어 이미지 프롬프트로 최적화 번역한 뒤 HF API로 전달하는 중첩 호출 방식을 사용합니다.

### 3.4 Pydantic
- **사용처**: `schemas/history_schema.py` 등 모든 데이터 유효성 검증.
- **이유**: AI의 응답은 비정형적일 수 있는데, Pydantic을 통해 강제적인 타입 체크와 `model_validate`를 수행하여 안정성을 확보했습니다.

---

## 4. 핵심 기능 흐름 (코드 추적 기반)

### 4.1 광고 문구 생성 흐름
1. **Trigger**: `app.py -> _run_text_generation()` 호출.
2. **Logic**: `TextService.generate_ad_copy()` 호출.
3. **Prompt**: `utils.prompt_builder.build_text_prompt()`에서 시스템/유저 프롬프트 생성.
4. **API Call**: OpenAI GPT 호출 및 `raw_text` 수신.
5. **Parsing**: `TextService._parse_response()`에서 정규표현식을 통해 "광고 문구"와 "홍보 문장" 섹션을 분리.
6. **Save**: `HistoryService.save_history()`를 통해 DB 저장.
7. **UI**: `st.session_state` 업데이트 후 문구 렌더링.

### 4.2 광고 이미지 생성 흐름
1. **Trigger**: `app.py -> _run_image_generation()`.
2. **Logic**: `ImageService.generate_ad_image()`.
3. **Optimizing**: GPT를 별도 호출하여 한국어 입력을 SDXL용 상세 영문 프롬프트로 번역 (`ImageService._api_response` 라인 139).
4. **API Call**: Hugging Face Inference API(POST 요청) 호출.
5. **Pillow**: 수신된 `bytes`를 처리하고 필요 시 `Image.alpha_composite` 등으로 데코레이션 (Mock 모드).
6. **Output**: `image_data` 바이너리 데이터를 UI에 전달.

### 4.3 인스타그램 업로드 흐름 (Meta Graph API)
1. **Trigger**: `app.py -> render...upload() -> st.button("🚀 올리기")`.
2. **Service**: `InstagramService.upload_real()` 제너레이터 실행.
3. **Hosting**: `freeimage.host` API를 호출하여 `image_bytes`를 public URL로 변환 (Meta API는 URL 형태만 수용).
4. **Media Cont**: Meta Graph API의 `/media` 엔드포인트에 `image_url`과 `caption` 전송하여 컨테이너 ID 획득.
5. **Publish**: `/media_publish` 엔드포인트를 호출하여 실제 피드에 배포.
6. **UI State**: 제너레이터의 `yield`를 통해 단계별 진행률을 UI에 실시간 표시.

---

## 5. 설계 의도 (코드 기반 설명)

- **Service 레이어 분리**: `TextService`, `ImageService` 등을 나누어 특정 API(예: OpenAI -> Anthropic)가 변경되어도 UI 코드인 `app.py`는 수정할 필요가 없도록 결합도를 낮췄습니다.
- **Prompt_builder 별도 분리**: 프롬프트는 엔지니어링 영역이므로 비즈니스 로직과 섞이지 않게 `utils/`에 순수 함수로 정의했습니다.
- **HistoryService의 독립성**: 비동기 DB 작업과 파일 시스템 저장 로직(`_save_history_impl` 라인 31)을 캡슐화하여 세션 관리 안정성을 도모했습니다.
- **Mock / 실제 API 모드**: `config/settings.py`의 `USE_MOCK` 플래그를 통해 비용 발생 없이 UI와 로직 흐름을 테스트할 수 있도록 설계했습니다.

---

## 6. 실제 문제와 해결 과정 (코드 기반)

### 6.1 DB Locked 및 세션 충돌 문제
- **문제**: Streamlit의 리런(Rerun) 특성상 세션 관리가 미흡하면 SQLite의 `database is locked` 에러가 빈번했습니다.
- **해결**: `HistoryService` 내에서 주입된 세션이 없을 경우 `AsyncSessionLocal()` 컨텍스트 매니저를 직접 생성하여 실행하고 즉시 닫히도록 완결성을 높였습니다 (`history_service.py` 라인 28).

### 6.2 비동기(Asyncio) 실행 루프 충돌
- **문제**: `asyncio.run()` 호출 시 이미 실행 중인 루프와 충돌하는 이슈.
- **해결**: `app.py`의 `run_async` 유틸리티에서 현재 스레드에 새 루프를 만들어 독립적으로 실행하는 구조를 취해 UI 스레드와의 간섭을 최소화했습니다.

---

## 7. 트레이드오프 (Trade-off)

- **장점**: 개발 속도가 매우 빠르며, `HistoryService`의 파일/DB 동시 저장 로직 등을 통해 서비스 로그를 완벽히 관리할 수 있습니다.
- **단점**: Streamlit은 사용자가 많아질수록 서버 메모리 사용량이 급증합니다.
- **결정 이유**: 현재 목표는 '사용 가능한 MVP'를 빠르게 시장에 내놓는 것이므로, 확장성보다는 개발 속도와 AI 응답 품질에 기술적 자원을 집중했습니다.

---

## 8. 개선 방향 (실무 관점)

1. **태스크 큐 도입**: 이미지 생성 등 수십 초가 소요되는 작업은 `Celery` + `Redis` 모델로 분리하여 사용자 경험을 개선해야 합니다.
2. **저장소 분리**: 현재 로컬 파일 시스템에 저장하는 이미지를 AWS S3 등으로 이전하여 확장성을 확보해야 합니다.
3. **Pydantic Structured Output**: 현재 정규표현식 파싱 방식에서 OpenAI의 `with_structured_output` API로 전환하여 응답 파싱의 100% 신뢰도를 확보할 예정입니다.

---

## 9. 면접 답변 템플릿 (핵심 요약)

- **Q: 이 프로젝트를 설명해주세요.**
    - **A**: "소상공인의 광고 제작 허들을 낮추기 위해 OpenAI와 Hugging Face API를 연동한 자동 콘텐츠 생성 및 인스타그램 업로드 서비스입니다. Layered 아키텍처를 적용해 로직과 UI를 분리했으며, 비동기 처리를 통해 생성 효율을 높인 Streamlit 기반 앱입니다."
- **Q: 왜 이 기술 스택을 선택했나요?**
    - **A**: "초기 MVP 단계에서의 운영 편의성과 배포 속도를 우선했습니다. SQLite와 Streamlit을 통해 개발 사이클을 단축하고, Pydantic과 SQLAlchemy를 사용하여 향후 서비스 규모 확장 시 유연하게 대응할 수 있도록 설계했습니다."
- **Q: 가장 어려웠던 문제와 해결 방법은?**
    - **A**: "비동기 처리가 필수적인 AI 서비스와 동기식인 Streamlit 환경을 통합하는 과정에서 발생하는 이벤트 루프 충돌이었습니다. 이를 전용 비동기 서비스 레이어와 독립 루프 호출 방식으로 해결하여 시스템 안정성을 확보했습니다."
- **Q: 이걸 서비스로 확장하면 어떻게 할 건가요?**
    - **A**: "현재 서버 블로킹 문제를 해결하기 위해 백그라운드 태스크 큐를 도입하고, 컨테이너 환경(Docker)과 클라우드 저장소를 활용해 가용성과 확장성을 높일 계획입니다."
