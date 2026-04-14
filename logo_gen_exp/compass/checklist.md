# checklist — logo_gen_exp

## 골격
- [x] `logo_gen_exp/` 폴더 생성
- [x] `compass/` 3파일
- [x] `README.md`
- [x] `.gitignore` 에 `logo_gen_exp/samples/` 추가

## 사이클 1: 프롬프트 순수 함수 (TDD)

### RED
- [x] `tests/__init__.py`
- [x] `tests/test_prompts.py`
  - [x] `test_includes_brand_name`
  - [x] `test_includes_color_hex`
  - [x] `test_english_name_uses_rounded_sans_serif`
  - [x] `test_korean_name_flags_hangul`
  - [x] `test_mixed_name_detected_as_korean`
  - [x] `test_forbids_illustrations_and_shadows`
  - [x] `test_mentions_mug_plate_printing_context`
- [x] pytest 모두 실패 확인 (prompts.py 미존재)

### GREEN
- [x] `prompts.py` — `build_logo_generation_prompt(name, color_hex)` 최소 구현
- [x] pytest 전부 통과 (12/12)

### REFACTOR
- [x] `_is_hangul(s)` 헬퍼 분리
- [x] 언어별 폰트 상수 분리 (ENGLISH_FONT, KOREAN_FONT)
- [x] 금지 규칙 상수 (FORBIDDEN_ELEMENTS)
- [x] pytest 여전히 통과

## 사이클 2: LogoGenerator (Fake 주입)

### RED
- [x] `tests/test_generator.py`
  - [x] `FakeImageClient` 정의
  - [x] `test_returns_bytes_from_client`
  - [x] `test_prompt_includes_name_and_color`
  - [x] `test_default_size_1024`
  - [x] `test_client_called_exactly_once`
- [x] pytest 실패 확인

### GREEN
- [x] `generator.py` — `ImageClientProtocol`, `LogoGenerator(client)` 구현
- [x] pytest 통과 (16/16)

### REFACTOR
- [x] 기본 size 상수 `DEFAULT_SIZE = "1024x1024"`

## 사이클 3: OpenAIImageClient (실제 어댑터)

- [x] `openai_client.py`
  - [x] `OpenAIImageClient(api_key, model="gpt-image-1-mini")`
  - [x] `generate_png(prompt, size) -> bytes`
  - [x] Langfuse `start_as_current_observation(name="logo.autogenerate", as_type="span")` 래핑
  - [x] span metadata 에 prompt / size / model 기록
  - [x] 키 미설정 시 nullcontext 폴백
  - [x] `last_trace_id` 속성으로 UI 에서 trace_id 표시 가능
- [ ] 수동 스모크 (Streamlit 실행 시 검증) — 📱 단계

## Streamlit 실험 페이지

- [x] `app_logo_lab.py`
  - [x] 입력 폼 (이름 / 색상 / 선택: 프롬프트 오버라이드)
  - [x] 생성 버튼
  - [x] 결과 영역 (st.image + 사용 프롬프트 표시 + trace_id)
  - [x] `samples/` 저장 로직 (timestamp+uuid 파일명 + 메타데이터 JSON)
  - [x] 최근 12개 히스토리 썸네일

## 📱 실사용 테스트

- [ ] `streamlit run logo_gen_exp/app_logo_lab.py` 기동 OK
- [ ] 영문명 생성 — 품질 OK
- [ ] 한글명 생성 — 한글 오탈자 없음
- [ ] 혼합명 생성
- [ ] 색상이 글자에 올바르게 반영
- [ ] 배경 순백 / 일러스트 없음
- [ ] 머그컵·접시 인쇄 적합성 육안 OK
- [ ] Langfuse 에서 `logo.autogenerate` trace 관찰 (input/output 포함)
- [ ] `samples/` 폴더에 결과 자동 저장됨

## 통합 준비

- [ ] 최종 프롬프트 문안 확정
- [ ] `services/logo_service.py` 이식 계획 메모
- [ ] `OnboardingService.finalize` 통합 지점 결정
