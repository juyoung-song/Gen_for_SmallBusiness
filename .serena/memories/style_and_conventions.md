# 코드 스타일 및 컨벤션

## 언어 및 타입
- Python 3.11+
- Type hints 사용 (함수 인자, 반환값)
- Pydantic 2.0 모델로 입출력 검증

## 네이밍
- 클래스: PascalCase (예: `TextService`, `Settings`, `ImageService`)
- 함수/메서드: snake_case (예: `generate_ad_copy`, `_mock_response`)
- 상수: UPPER_SNAKE_CASE (예: `_MOCK_DATA`, `TONE_DISPLAY_MAP`)
- private/내부 메서드: `_` 접두사 (예: `_api_response`, `_parse_response`)

## 독스트링
- 클래스/주요 메서드에 한국어 독스트링 사용 (예: `"""애플리케이션 전체 설정."""`)

## 비동기 처리
- SQLAlchemy async 세션 (`aiosqlite`)
- `asyncio` 이벤트 루프를 `run_async()` 헬퍼로 Streamlit에서 실행

## Mock 패턴
- 서비스 클래스 내부에 `_mock_response()` / `_api_response()` 분리
- `settings.USE_MOCK` 플래그로 분기

## 구조 원칙
- 계층 분리: UI(app.py) → services → models/schemas
- 설정은 `config/settings.py`의 싱글턴 `get_settings()`로 주입
- 에러 클래스: 각 서비스마다 `XxxServiceError` 정의 (예: `TextServiceError`, `ImageServiceError`)
