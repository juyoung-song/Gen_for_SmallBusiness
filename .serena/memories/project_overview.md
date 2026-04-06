# 프로젝트 개요: Gen_for_SmallBusiness

## 목적
소상공인(1인 사업자, 초기 창업자)을 위한 AI 광고 콘텐츠 생성 + 인스타그램 자동 업로드 서비스.
- 상품명/설명/스타일 입력 → GPT로 광고 문구 생성 + Hugging Face로 광고 이미지 생성
- 생성된 콘텐츠를 인스타그램 피드/스토리로 자동 업로드
- 생성 히스토리 SQLite DB에 저장

## 기술 스택
- **Language**: Python 3.11+
- **Frontend/UI**: Streamlit 1.30+
- **Data validation**: Pydantic 2.0+, Pydantic-Settings 2.0+
- **Database/ORM**: SQLAlchemy 2.0+ (async), aiosqlite (SQLite)
- **AI APIs**: OpenAI (GPT, 텍스트 생성 + 영문 번역), Hugging Face (FLUX/SDXL, 이미지 생성)
- **Image processing**: Pillow (JPEG 변환, Mock 모드)
- **Instagram 연동**: requests (Meta Graph API + FreeImage.host)
- **HTTP**: httpx
- **Package manager**: uv (pyproject.toml 기반)
