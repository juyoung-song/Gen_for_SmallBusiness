# 코드베이스 구조

## 디렉토리
```
app.py                      # Streamlit 메인 앱 (탭: 새로 만들기 / 히스토리 아카이브)
config/
  settings.py               # Pydantic-Settings, .env 로드 (Settings 클래스, get_settings(), setup_logging())
  database.py               # SQLAlchemy 비동기 세션 팩토리, DB 초기화
models/
  base.py                   # TimestampMixin + ORM Base
  history.py                # History 테이블 ORM 모델
schemas/
  text_schema.py            # 텍스트 생성 입출력 Pydantic 모델
  image_schema.py           # 이미지 생성 입출력 Pydantic 모델
  history_schema.py         # 히스토리 DB 입출력 Pydantic 모델
  instagram_schema.py       # 인스타그램 업로드 관련 Pydantic 모델
services/
  text_service.py           # TextService: generate_ad_copy(), _mock_response(), _api_response(), _parse_response()
  image_service.py          # ImageService: generate_ad_image(), compose_story_image(), _api_response(), _mock_response()
  instagram_service.py      # InstagramService: upload_story(), upload_real(), upload_mock(), _upload_impl()
  history_service.py        # DB 히스토리 삽입/조회
  caption_service.py        # 인스타그램 캡션 생성
utils/
  prompt_builder.py         # 사용자 입력 → AI 프롬프트 변환
docs/                       # PRD, 아키텍처, 스택 문서
```

## app.py 주요 함수
- `setup_database()`: DB 초기화
- `run_async()`: asyncio 이벤트 루프 실행 헬퍼
- `render_instagram_preview_and_upload()`: 피드 업로드 UI
- `render_instagram_story_preview_and_upload()`: 스토리 업로드 UI
- `_run_text_generation()`: 텍스트 생성 로직
- `_run_image_generation()`: 이미지 생성 로직
- `_run_combined_generation()`: 텍스트+이미지 동시 생성
- `_fetch_histories()`: 히스토리 조회

## Settings 주요 속성 (config/settings.py)
- `USE_MOCK: bool = True` — Mock/실제 API 전환
- `OPENAI_API_KEY`, `HUGGINGFACE_API_KEY`
- `META_ACCESS_TOKEN`, `INSTAGRAM_ACCOUNT_ID`
- `TEXT_MODEL`, `IMAGE_MODEL`, `IMAGE_SIZE`, `IMAGE_QUALITY`
- `is_api_ready`, `is_huggingface_ready`, `is_instagram_ready` (property)
