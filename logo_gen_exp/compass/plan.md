# plan — logo_gen_exp

## 목표

브랜드 이름 + 색상 → AI 로고 자동 생성의 **프롬프트 문안** 과 **구조(의존 주입)** 를 실험으로 확정.

## 단계

### ✅ 1. 폴더 골격 + 문서
- [x] `logo_gen_exp/` 디렉터리 생성
- [x] `compass/context.md` / `plan.md` / `checklist.md`
- [x] `README.md`
- [x] `.gitignore` 에 `logo_gen_exp/samples/` 추가

### ✅ 2. TDD 사이클 1 — build_logo_generation_prompt (순수 함수)
- [x] RED: `tests/test_prompts.py` 작성 (실패 상태)
  - 브랜드명 포함
  - 색상 hex 포함
  - 영문명 → rounded sans-serif 포함, Korean 미포함
  - 한글명 → Korean / Hangul 명시
  - 혼합명 → 한글 감지
  - illustrations / shadows / 3D 금지 명시
  - mug / plate / packaging 인쇄 컨텍스트 명시
- [ ] GREEN: `prompts.py` 최소 구현
- [ ] REFACTOR: 상수 분리, `_is_hangul` 헬퍼

### ✅ 3. TDD 사이클 2 — LogoGenerator (Fake 주입)
- [ ] RED: `tests/test_generator.py`
  - FakeImageClient 가 받은 prompt 에 브랜드명·색상 포함
  - size = "1024x1024"
  - bytes 그대로 반환
- [ ] GREEN: `generator.py` — `LogoGenerator(client)` 구현
- [ ] REFACTOR: 기본 size 상수화

### ✅ 4. OpenAIImageClient 실제 어댑터 + Langfuse
- [ ] `openai_client.py` — `images.generate` 호출
- [ ] Langfuse `start_as_current_observation(name="logo.autogenerate")` 로 감쌈
- [ ] trace_id 노출 (Streamlit 에서 표시)

### ✅ 5. Streamlit 실험 페이지
- [ ] `app_logo_lab.py`
  - 입력: 이름 / 색상
  - 생성 버튼 → LogoGenerator 호출
  - 결과: 이미지 + 프롬프트 + trace_id
  - `samples/` 에 저장 + 최근 N개 썸네일

### ✅ 6. 📱 실사용 테스트 (1차)
- [x] `streamlit run logo_gen_exp/app_logo_lab.py` 기동 확인
- [x] OpenAI API 호출 성공 (모델 교체 후)
- [x] 로고 이미지 생성 · samples/ 저장 확인
- [ ] 한/영/혼합 3종 생성 품질 비교 (다음 세션)
- [ ] Langfuse 에서 `logo.autogenerate` trace 관찰 (다음 세션)
- [ ] 머그컵·접시 인쇄 적합성 육안 평가 (다음 세션)

### ⏳ 7. 통합 결정 (미완)
- [ ] 결과 만족 시 `services/logo_service.py` 로 이식 계획 수립 (별도 CP)
- [ ] 불만족 시 프롬프트 재실험 또는 모델 교체 (Gemini/Nano Banana)

## 결정 변경 이력

- (초안) 별도 CLI `run.py` 불필요 — Streamlit 실험 페이지로 통합.
- (초안) 테스트는 실험 자기완결 (`logo_gen_exp/tests/`).
- (1차 스모크) `gpt-image-1` → **`gpt-image-1-mini`** 로 기본 모델 교체 (비용 절감).
- (1차 스모크) `response_format` 파라미터 제거 — `gpt-image-1*` 는 지원 안 함, 항상 b64_json 반환.
- (1차 스모크) Streamlit 이 `app_logo_lab.py` 를 직접 실행할 때 `logo_gen_exp` 패키지를 못 찾는 문제 → 파일 상단에서 프로젝트 루트를 `sys.path` 에 삽입.
