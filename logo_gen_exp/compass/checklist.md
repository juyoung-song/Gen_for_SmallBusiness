# checklist — logo_gen_exp

## 골격
- [x] `logo_gen_exp/` 폴더 생성
- [x] `compass/` 3파일
- [x] `README.md`
- [x] `.gitignore` 에 `logo_gen_exp/samples/` 추가

## 사이클 1: 프롬프트 순수 함수 (TDD)
- [x] RED / GREEN / REFACTOR
- [x] pytest 12/12

## 사이클 2: LogoGenerator (Fake 주입)
- [x] RED / GREEN / REFACTOR
- [x] pytest 4/4

## 사이클 3: OpenAIImageClient (실제 어댑터 + Langfuse)
- [x] `generate_png`
- [x] `edit_png` (사이클 6에서 추가)
- [x] `span_name` 파라미터화 (사이클 11)
- [x] Langfuse `start_as_current_observation` 래핑, 키 미설정 시 nullcontext 폴백
- [x] `last_trace_id` UI 노출

## 사이클 4: PIL 폰트 렌더링
- [x] RED: `tests/test_pil_renderer.py`
- [x] GREEN: `pil_renderer.py::render_wordmark`
- [x] LXGW WenKai KR 6종 번들
- [x] Streamlit 🔤 PIL 모드
- [x] pytest 9/9

## 사이클 5: build_edit_prompt
- [x] RED / GREEN
- [x] 빈·공백 입력 거부
- [x] pytest 추가 케이스 통과

## 사이클 6: PilPlusAiEditor (Fake 주입)
- [x] RED: `tests/test_pil_plus_ai.py`
- [x] GREEN: `pil_plus_ai.py` + ImageClientProtocol.edit_png 확장
- [x] Streamlit 🎨 PIL+AI 변형 모드

## 사이클 7: edit 프롬프트 재설계
- [x] 배경/장식 전면 금지 테스트 갱신
- [x] `_EDIT_PRESERVATION_CLAUSE` / `_EDIT_ALLOWED_SCOPE` 재작성
- [x] pure white 강제 + 타이포 조정만 허용

## 사이클 11: Raw 모드
- [x] `edit_png(span_name=...)` 파라미터화
- [x] Streamlit 🔥 Raw 모드 (시스템 가드 없이 사용자 프롬프트 그대로)
- [x] Langfuse span 이름 분리: `logo.autogenerate` / `logo.pil_plus_ai_edit` / `logo.raw_edit`

## 📱 실사용 테스트

### 1차 (AI 모드, gpt-image-1-mini)
- [x] Streamlit 기동
- [x] OpenAI API 호출 성공
- [x] 로고 생성 + samples 저장

### 2차 (PIL 모드)
- [x] 한글/영문/혼합 이름 정확 렌더
- [x] 색상 반영 / 순백 배경

### 3차 (Edit / Raw 모드) — 일부만 확인
- [ ] `g만 크게`, `들쭉날쭉` 등 변형 지시 결과 품질 — **사유**: PIL 채택 결정으로 본 실험 범위 축소
- [ ] Langfuse trace 관찰 — CP15+ 이미지 전환 시 재검증 예정

## 실험 결론 (production 이식 여부)

- [x] **채택**: PIL 폰트 렌더링 (`pil_renderer.py::render_wordmark`)
  - 근거: 결정적·비용 0·한글 정확·배경 순백 완벽 보장
- [x] **비채택**: gpt-image-1-mini (generate / edit / raw edit)
  - 근거: 배경 장식 오염, 제어 어려움, 비용 발생
  - 보류: CP15+ 이미지 백엔드 전환 시 multi-input 으로 재도입 검토

## 다음 단계 (별도 CP)

- [ ] **CP14**: `services/logo_service.py` 이식
  - [ ] 폰트 이동: `logo_gen_exp/LXGWWenKaiKR-Medium.ttf` + `OFL.txt` → `assets/fonts/`
  - [ ] `render_wordmark` + `LogoAutoGenerator` 신설
  - [ ] `BrandDraft.with_logo_path` 추가
  - [ ] `OnboardingService.finalize` 통합 — `logo_path is None` 이면 자동 생성
  - [ ] `ui/onboarding.py` `_persist_draft` 에 `LogoAutoGenerator` 주입
  - [ ] 테스트 이식
  - [ ] 📱 실사용 스모크
- [ ] **CP15+**: 이미지 생성 백엔드 `gpt-image-1-mini` 로 전환, multi-input 로고 주입
