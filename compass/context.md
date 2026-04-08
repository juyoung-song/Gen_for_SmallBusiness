# Context

> **작성일:** 2026-04-08
> **마지막 갱신:** 2026-04-08 (Step 1.1 완료, Step 1.2 진행 중 — TDD 도입)
> **브랜치:** `refactor/won/main` (분기점: `2c808e0`, 2026-04-06)
> **이전 버전 폐기:** IP-Adapter 리뷰 컨텍스트(2026-04-03)는 본 문서로 대체됨

---

## 1. 프로젝트 한 줄

소상공인이 **브랜드 일관성을 유지**하면서 인스타그램 광고 콘텐츠를 자동 생성·게시하도록 돕는 Streamlit 서비스.

## 2. 본 리팩터링의 목표

`docs/design.md` 의 결정 사항에 맞춰 **현재 코드베이스를 정리**하는 것이 최우선이고, 이어서 **MVP 완성**까지 단계적으로 진행한다.

- **Phase 1 (리팩터링)**: 기존 코드를 design.md 구조로 정렬
- **Phase 2 (MVP 완성)**: 온보딩, 데이터 모델, 참조 이미지 풀 등 design.md에 정의됐으나 미구현인 기능 추가

## 3. 핵심 설계 결정 (design.md 발췌)

- **brand_image.txt**: 온보딩 1회 GPT 자동 생성 + 사용자 검수 → 이후 **불변** (system prompt 역할)
- **상품 ↔ 참조 이미지**: 같은 상품의 "화장 전(raw)" / "화장 후(generated_upload)" 부모-자식 관계
- **참조 이미지 풀**: 인스타에 게시 완료된 결과만 편입. 매번 광고 생성 시 갤러리에서 선택 가능 (옵션, 다중 선택, 전체 풀)
- **신상품 판별**: 사용자 명시 토글
- **광고 목적**: 카테고리 6종 칩 + 자유 텍스트
- **사용자 대기 시간 최소화**: 파일은 즉시 staging 저장, DB row는 생성 후 백그라운드
- **단일 사용자 가정**: 멀티테넌트는 v2 이후
- **인스타 자동 게시**: Meta Graph API + 사전 인증 완료

## 4. 모듈 구조 원칙

> "**1 모듈 = 1 파일** + 공통 인터페이스"

- 백엔드(이미지/텍스트 생성기)는 새 디렉토리 `backends/` 에 평탄 구조로 모음
- 베이스 클래스/프로토콜 1개 정의 → 각 백엔드 파일이 구현
- 신규 모델 추가 = 새 파일 1개 추가
- ORM 모델은 기존 `models/` 디렉토리에 유지 (백엔드와 분리)

```
backends/                  # 이미지/텍스트 생성 백엔드 (Step 1.1 ✅)
  __init__.py
  image_base.py            # ImageBackend Protocol
  text_base.py             # TextBackend Protocol
  registry.py              # 환경 변수 기반 백엔드 선택 팩토리
  hf_sd15.py               # SD 1.5 txt2img (HFSD15Backend)
  hf_ip_adapter.py         # SD 1.5 + IP-Adapter
  hf_img2img.py            # SD 1.5 img2img
  hf_hybrid.py             # IP-Adapter + img2img 하이브리드
  hf_inference_api.py      # Hugging Face Serverless Inference API
  openai_gpt.py            # OpenAI GPT (텍스트)
  remote_worker.py         # 자체 원격 워커 클라이언트 (worker_api.py 호출)
  mock_image.py
  mock_text.py
  # 추후 추가 예정 (Phase 2 이후): hf_flux.py, nano_banana.py 등

models/                    # ORM (Step 1.2 진행 중)
  __init__.py
  base.py                  # Base + TimestampMixin
  brand_image.py           # (신규 ✅) 브랜드 정체성 (불변)
  product.py               # (신규 ✅) 상품 + raw 이미지
  generated_upload.py      # (신규 ✅) 생성 결과 + 인스타 메타
  history.py               # (legacy, Phase 2 종료 후 제거)

tests/                     # pytest 인프라 (Step 1.2 ✅)
  __init__.py
  conftest.py              # 인메모리 SQLite + async 세션 fixture
  test_models/
    test_brand_image.py    # 3 passed
    test_product.py        # 2 passed
    test_generated_upload.py  # 4 passed
  test_services/           # (TDD 진행 예정)
```

## 5. 현재 코드베이스 분석 요약

### 잘 구현된 부분 (그대로 유지)
- **서비스 레이어**: `TextService`, `ImageService`, `CaptionService`, `InstagramService`, `HistoryService` 단일 책임 분리 양호
- **Mock/API 이중 모드**: `USE_MOCK` 플래그로 환경 전환
- **Pydantic 2.0 검증**: `field_validator` 활용
- **로컬 모델 백엔드**: `models/sd15.py`, `models/ip_adapter.py`, `models/img2img.py`, `models/hybrid.py` 이미 프로토콜 기반
- **인스타 업로더**: FreeImage 호스팅 + Meta Graph API v19.0 흐름 안정
- **async DB 인프라**: SQLAlchemy 2.0 + aiosqlite

### 갭 (design.md 대비 미구현/불일치)

| 영역 | 현 상태 | design.md 요구 |
|------|---------|---------------|
| **온보딩 화면** | 없음 | 자유 텍스트 + 인스타 URL → 캡처 → GPT Vision 분석 → brand_image.txt 생성 → 검수 |
| **brand_image ORM** | 없음 | 단일, 불변, system prompt 저장 |
| **product ORM** | 없음 | 상품 + raw_image 관계 |
| **generated_upload ORM** | 없음 (History만 존재) | 생성 결과 + 인스타 메타데이터 + 참조 이미지 풀 |
| **상품명 입력 UI** | 자유 텍스트 | 드롭다운 + 신상품 토글 |
| **광고 목적 UI** | 단일 드롭다운 | 칩 6종 + 자유 텍스트 |
| **참조 이미지 UI** | 매번 새 업로드 | 갤러리 (전체 풀에서 다중 선택) |
| **신상품 토글** | 없음 | raw 이미지 업로드 조건부 필수화 |
| **백엔드 디렉토리** | `models/` 에 ORM과 혼재 | `backends/` 로 분리 |
| **인스타 캡처 모듈** | `crawl_and_analyze/image_crawler.py` (instaloader, 로그인 차단) | `browser-use` CLI 기반으로 교체 (다른 브랜치에 이미 구현됨) |

### 다른 브랜치에 살아있는 자산

| 브랜치 | 자산 | 본 리팩터링에서 활용 방법 |
|--------|------|------------------------|
| `feature/won/insta-snapshot` | `scripts/insta_screenshot.py` (browser-use CLI) | 온보딩 단계의 캡처 모듈로 통합 |
| `enhance/won/img-generation` | 배경 교체, FLUX fallback | 이미지 생성 백엔드 옵션으로 통합 (`backends/hf_flux.py` 등) |

## 6. 비기능 요구사항

- **응답 속도**: 광고 생성 버튼 → 결과 표시까지 가능한 한 단축. DB I/O는 백그라운드로
- **유지보수성**: 모델 추가/교체가 잦으므로 1파일 1모듈 + 공통 인터페이스 엄수
- **단일 사용자 가정**: 단, brand_image 등은 향후 멀티테넌트 확장을 막지 않는 스키마로 (`user_id` 컬럼 둠)
- **TDD (Step 1.2 부터)**: 신규 production 코드는 RED → GREEN → REFACTOR.
  superpowers `test-driven-development` 스킬을 따른다. Iron Law: NO PRODUCTION CODE WITHOUT A FAILING TEST FIRST.
  단, 단순 이동/이름 변경은 회귀 검증으로 갈음 (Step 1.1 처럼).

## 7. 비범위 (Out of Scope)

- 매 광고 후 brand_image.txt 갱신 (불변 정책)
- "사용자 선호 학습" 피드백 루프 (v2)
- 멀티테넌트, 사용자 인증
- Instagram Stories 차별화 (피드 우선)
- 매 광고 시 결과물 GPT Vision 재분석 (불필요)

## 8. 참고 문서

- [`docs/design.md`](../docs/design.md) — **최우선** 설계 문서
- [`docs/PRD.md`](../docs/PRD.md) — 초기 기획 (구 버전, design.md와 충돌 시 design.md 우선)
- [`docs/architecture.md`](../docs/architecture.md) — 초기 아키텍처 (구 버전, 동일)
