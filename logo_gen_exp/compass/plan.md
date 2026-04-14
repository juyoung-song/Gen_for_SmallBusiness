# plan — logo_gen_exp

## 목표

브랜드 이름 + 색상 → 로고 생성의 **프롬프트 문안과 구조** 를 실험으로 확정.

본 실험의 결론: **PIL 폰트 렌더링** 경로만 production 으로 이식.
AI 모드 (gpt-image-1-mini generate / edit / raw edit) 는 실험 폴더에만 남기고 비교 참고용으로 유지.

## 단계

### ✅ 1. 폴더 골격 + 문서

- [x] `logo_gen_exp/` 디렉터리 생성
- [x] `compass/context.md` / `plan.md` / `checklist.md`
- [x] `README.md`
- [x] `.gitignore` 에 `logo_gen_exp/samples/` 추가

### ✅ 2. TDD 사이클 1 — build_logo_generation_prompt (순수 함수)

- [x] RED: `tests/test_prompts.py` 작성 (실패 상태)
- [x] GREEN: `prompts.py` 최소 구현
- [x] REFACTOR: 상수 분리, `_is_hangul` 헬퍼

### ✅ 3. TDD 사이클 2 — LogoGenerator (Fake 주입)

- [x] RED: `tests/test_generator.py`
- [x] GREEN: `generator.py` — `LogoGenerator(client)` 구현
- [x] REFACTOR: 기본 size 상수화

### ✅ 4. OpenAIImageClient 실제 어댑터 + Langfuse

- [x] `openai_client.py` — `images.generate` 호출
- [x] Langfuse `start_as_current_observation` 래핑
- [x] last_trace_id 노출

### ✅ 5. Streamlit 실험 페이지 (초안)

- [x] `app_logo_lab.py` — AI 모드 기반

### ✅ 6. 📱 실사용 테스트 (1차 — gpt-image-1 AI 모드)

- [x] `streamlit run logo_gen_exp/app_logo_lab.py` 기동 확인
- [x] OpenAI API 호출 성공 (모델 교체 후)
- [x] 로고 이미지 생성 · samples/ 저장 확인

### ✅ 7. TDD 사이클 4 — PIL 폰트 렌더링 모드

- [x] RED: `tests/test_pil_renderer.py`
- [x] GREEN: `pil_renderer.py` — `render_wordmark(name, color_hex, font_path)`
- [x] Streamlit 에 🔤 PIL 모드 추가
- [x] LXGW WenKai KR 시리즈 6종 폰트 번들
- [x] 📱 실사용 테스트: 한글/영문/혼합 모두 정확 렌더 확인

### ✅ 8. TDD 사이클 5 — build_edit_prompt

- [x] RED → GREEN → REFACTOR
- [x] 빈 입력·공백 입력 거부
- [x] preservation clause + allowed scope 구조

### ✅ 9. TDD 사이클 6 — PilPlusAiEditor

- [x] RED: `tests/test_pil_plus_ai.py` (Fake 주입)
- [x] GREEN: `pil_plus_ai.py` — PIL 베이스 + OpenAI edit 파이프라인
- [x] `OpenAIImageClient.edit_png` + `span_name` 파라미터
- [x] Streamlit 🎨 PIL+AI 변형 모드 추가

### ✅ 10. TDD 사이클 7 — edit 프롬프트 재설계

- **배경**: `들쭉날쭉`, `g만 크게` 같은 입력에 배경 텍스처/장식(잎·프레임)이 생기는 문제 관찰.
- [x] RED: 배경/장식 전면 금지 테스트 갱신
- [x] GREEN: `_EDIT_PRESERVATION_CLAUSE` / `_EDIT_ALLOWED_SCOPE` 재작성 — pure white background 강제 + 타이포 조정(자간·굵기·기울기·개별 글자 크기)만 허용

### ✅ 11. Raw 모드 + span_name 파라미터화

- [x] `edit_png(span_name="logo.raw_edit")` 로 별도 trace 분리
- [x] Streamlit 🔥 Raw 모드 — 시스템 가드 없이 사용자 프롬프트 그대로

### 🟡 12. 📱 실사용 테스트 (3차 — Edit/Raw 모드)

- [ ] `g만 크게` / `들쭉날쭉` / `자간 좁혀서` / `기울여서` 등 입력으로 Edit 모드 결과 확인
- [ ] Raw 모드와 A/B 비교
- [ ] Langfuse 에서 `logo.pil_plus_ai_edit` / `logo.raw_edit` 각각 observation 확인

> **사유 명시**: 본 실험의 결론은 이미 "PIL 모드만 production 이식" 으로 결정됨. Edit/Raw 모드의 상세 품질 검증은 실험 참고용이라 일부만 체크됨. 완전 통과는 CP15+ 이미지 백엔드 전환 시 재수행.

### 📦 13. 실험 결론 및 다음 단계

- ✅ **채택**: PIL 폰트 렌더링 (결정적, 비용 0, 한글 정확)
- ❌ **비채택**: gpt-image-1-mini generate/edit (결과 품질 편차 크고, 장식 오염, 배경 변형 등 제어 어려움)
- 🔜 **CP14** (별도): PIL 렌더러를 `services/logo_service.py` 로 이식, `OnboardingService.finalize` 에서 `logo_path` 없으면 자동 생성
- 🔜 **CP15+** (별도): 이미지 생성 백엔드를 `gpt-image-1-mini` 로 전환 + multi-input 으로 상품 사진 + 로고 동시 주입

## 결정 변경 이력

- (초안) 별도 CLI `run.py` 불필요 — Streamlit 실험 페이지로 통합.
- (초안) 테스트는 실험 자기완결 (`logo_gen_exp/tests/`).
- (1차 스모크) `gpt-image-1` → **`gpt-image-1-mini`** 로 기본 모델 교체 (비용 절감).
- (1차 스모크) `response_format` 파라미터 제거 — `gpt-image-1*` 는 지원 안 함.
- (1차 스모크) `sys.path` 에 프로젝트 루트 삽입 — streamlit 직접 실행 호환.
- (사이클 7) edit 프롬프트 재설계: 배경/장식 전면 금지, 타이포 조정만 허용.
- (사이클 11) `OpenAIImageClient.edit_png` 에 `span_name` 파라미터 추가 → Edit/Raw 모드 trace 분리.
- **(최종 결론)** PIL 모드만 production 으로 이식. AI 모드들은 실험 폴더에 아카이브.
