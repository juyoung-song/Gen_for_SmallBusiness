# Context

## 프로젝트 개요
소상공인을 위한 AI 광고 콘텐츠 생성 + 인스타그램 자동 업로드 Streamlit 서비스 (MVP).

## 기술 스택
- Python 3.11+, Streamlit 1.30+
- OpenAI (GPT 텍스트 생성 + 한글→영어 번역)
- Hugging Face FLUX/SDXL (이미지 생성)
- SQLAlchemy 2.0 async + aiosqlite (SQLite 히스토리)
- Pydantic 2.0 (입출력 검증)
- Meta Graph API + FreeImage.host (인스타그램 업로드)

## 코드 리뷰 수행일
2026-04-03

## 리뷰 대상 커밋
- Base: `8540f72` (origin/main, MVP 오류 수정)
- Head: `dd7cfd6` (won 브랜치)

## 주요 발견 사항 요약
MVP 구조는 전반적으로 양호하나, 보안 취약점 1건, 런타임 버그 1건, 누락된 의존성 1건 등 Critical 이슈 3건이 존재함. Important 이슈 5건, 개선 제안 3건 추가 식별.

## 로컬 이미지 생성 모델 (IP-Adapter 기능 추가 예정)

### 선택 배경
- 현재 HF Serverless API는 사용자 업로드 사진을 실제로 반영하지 못함 (`has_reference=True` 플래그만 존재, 이미지 픽셀은 미전달)
- IP-Adapter + SD 1.5 조합으로 참조 이미지의 색감·구도·분위기를 직접 이미지 생성에 반영

### 환경
- MacBook Air M3 16GB (로컬 추론, MPS 백엔드)
- SD 1.5 모델: ~2GB, IP-Adapter 어댑터: ~280MB, 총 메모리 ~4GB
- 추론 속도: 30~60초/장

### 설계 원칙
- `models/` 디렉토리에 모델별 파일 분리 (`sd15.py`, `ip_adapter.py`)
- `ImageService`는 모델을 직접 알지 못하고 `LocalImageBackend` 인터페이스만 사용
- 향후 다른 모델 추가 시 `models/` 에 파일 하나만 추가하면 됨

---

## 잘 구현된 부분
- 서비스 레이어 단일 책임 분리 (TextService, ImageService, CaptionService, InstagramService, HistoryService)
- Mock/API 이중 모드 (`USE_MOCK` 플래그)
- Pydantic 2.0 `field_validator` 입력 검증
- 커스텀 예외 계층 (`TextServiceError`, `ImageServiceError`)
- SQLAlchemy 2.0 async ORM 패턴 (`Mapped`, `mapped_column`, `TimestampMixin`)
- `prompt_builder.py` 순수 함수 분리
