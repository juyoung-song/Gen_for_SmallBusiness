# context — logo_gen_exp

## 배경

메인 서비스의 이미지 생성 프롬프트는 온보딩 Vision 분석 결과(`brands.style_prompt`) 안에 "머그컵·접시·포장에 브랜드 로고를 각인한다" 는 **강제 규칙**을 담는다. 그런데 현재는:

- 로고 업로드는 옵셔널 → 약 상당수 사용자가 `brands.logo_path = NULL`
- 이 경우 이미지 모델(특히 나노바나나/SD/FLUX)은 "무슨 로고를 각인해야 할지" 모름 → 강제 규칙이 무의미

## 해결 방향

**로고 파일이 없으면 온보딩 확정 시점에 브랜드 이름 + 색상만으로 간단 타이포그래피 로고를 AI 로 1회 생성·저장.**

- 이미지 생성 시 항상 `logo_path` 가 존재한다고 가정 가능
- 후속 단계(IP-Adapter / 참조 이미지 주입) 에서도 로고를 참조 가능

본 실험 폴더는 **메인 코드 통합 전 프롬프트 문안 확정과 모델 결과 검증** 을 위한 격리된 공간.

## 설계 결정

### 1. 별도 폴더 (`logo_gen_exp/`)
- 메인 `services/` 에 바로 넣지 않고 실험 자기완결 폴더 유지.
- 테스트도 `logo_gen_exp/tests/` — 프로젝트 루트 `pytest` 에 섞이지 않음.
- 실험 완료 후 `services/logo_service.py` 로 이식.

### 2. 의존성 주입 구조
- `LogoGenerator(client: ImageClientProtocol)` 로 분리
  - 단위 테스트: `FakeImageClient` 주입 → 결정적·오프라인
  - 실제 실행: `OpenAIImageClient` 주입 → 실제 API 호출
- 프롬프트 빌더는 모듈 함수 (`build_logo_generation_prompt`) — 상태 없음, 순수 함수.

### 3. 모델 선택
- 1차 후보: **`gpt-image-1-mini`** (OpenAI)
  - 이유: 기존 `OPENAI_API_KEY` 재사용, 한/영문 타이포 둘 다 양호, 온보딩 1회 호출이라 비용 무시.
- 대안: Nano Banana (Gemini) — 별도 키 필요, 추후 비교.

### 4. Langfuse 추적
- `LANGFUSE_PUBLIC_KEY`/`SECRET_KEY` 환경변수 주입 전제.
- `langfuse.openai` wrapper 가 `images.generate` 를 자동 감쌀지 불확실 → 수동 `start_as_current_observation(name="logo.autogenerate", as_type="span")` 로 감싸고 그 안에서 OpenAI 호출.
- Observation 이름: `logo.autogenerate` (추후 이식 시 동일 이름 유지).

### 7. 구현 중 변경 사항 (1차 스모크 반영)
- `DEFAULT_MODEL` 을 `gpt-image-1-mini` 로 변경 (비용 절감, mini 에서도 품질 평가 충분).
- `response_format="b64_json"` 파라미터 **제거** — `gpt-image-1*` 계열은 해당 파라미터를 받지 않음. API 는 항상 b64_json 반환.
- Streamlit 직접 실행 시 `logo_gen_exp` 패키지 import 불가 문제 → `app_logo_lab.py` 상단에서 프로젝트 루트를 `sys.path` 에 삽입.

### 5. 프롬프트 설계 원칙 (실험 시작 시점)
- 언어 분기: 한글 문자 포함 여부로 영문 / 한글(Hangul) 분기 (`re.search(r"[\uAC00-\uD7A3]", name)`).
- 공통 규칙:
  - ONLY text wordmark — 일러스트·아이콘·배경·그림자·3D 전부 금지
  - 브랜드 색상: 글자 색으로, 배경은 순백
  - 컵·접시·포장에 프린트 가능한 단순 벡터 스타일
  - 부드러운/둥근 폰트 톤 (rounded sans-serif / soft Hangul)
- 정방형 1024×1024.

### 6. Streamlit 실험 페이지
- `logo_gen_exp/app_logo_lab.py` — 메인 `app.py` 와 분리.
- 입력: 브랜드명 / 컬러피커 / (선택) 프롬프트 오버라이드
- 결과: 생성 이미지 + 사용된 프롬프트 + Langfuse trace URL
- `samples/` 폴더에 결과 파일 자동 저장.

## 통합 지점 (실험 후)

성공 시 다음처럼 메인으로 이식:
- `services/logo_service.py` — `LogoGenerator` + prompt builder 이전
- `services/onboarding_service.py:OnboardingService.finalize` 에서 `draft.logo_path is None` 이면 자동 생성 호출
- `BrandDraft` 에 `with_logo_path()` 추가
- 관련 테스트 `tests/test_services/test_logo_service.py`
