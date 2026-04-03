# 개발 주요 명령어

## 실행
```bash
# 가상환경 활성화 (venv 또는 uv)
source .venv/bin/activate

# Streamlit 앱 실행
streamlit run app.py

# uv로 패키지 설치
uv sync
# 또는
pip install -r requirements.txt
```

## 환경 변수
```bash
cp .env.example .env
# .env 편집 후 streamlit 서버 재시작 필요
```

## Mock 모드 전환
- `.env`에서 `USE_MOCK=true` → 로컬 더미 데이터 반환 (API 키 불필요)
- `.env`에서 `USE_MOCK=false` → 실제 OpenAI/HuggingFace API 호출

## 유틸 명령어 (Darwin/macOS)
```bash
git status / git log / git diff
ls -la
find . -name "*.py"
grep -r "keyword" .
```

## 테스트/린트/포맷
- 현재 별도 테스트 프레임워크 미설정 (MVP 단계)
- 코드 스타일: PEP8, type hints 사용
