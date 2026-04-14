# logo_gen_exp — AI 로고 자동 생성 실험

온보딩 단계에서 사용자가 로고 파일을 제출하지 않은 경우, **브랜드 이름 + 브랜드 색상**만으로 간단한 타이포그래피 로고를 AI 로 자동 생성하기 위한 **실험 폴더**.

메인 코드(`services/`, `app.py`) 와 완전 분리. 실험이 끝나고 검증되면 `services/logo_service.py` 로 정식 이식 예정.

## 목적

- 이미지 생성 시 "컵·접시·포장에 브랜드 로고 각인" 지시가 **로고 파일이 없을 때 무의미해지는 문제** 해결.
- 로고 프롬프트 변형을 실험하며 최적 문안 확정.

## 디렉터리

```
logo_gen_exp/
  compass/
    context.md   설계/기술 결정
    plan.md      진행 계획 + 실사용 테스트 체크리스트
    checklist.md 상세 체크
  prompts.py     build_logo_generation_prompt (순수 함수)
  generator.py   LogoGenerator + ImageClientProtocol
  openai_client.py  OpenAIImageClient (실제 OpenAI + Langfuse span)
  app_logo_lab.py   Streamlit 실험 페이지
  samples/       생성 결과 (gitignore)
  tests/         자기완결 pytest
```

## 실행

```bash
# 테스트
pytest logo_gen_exp/tests/ -q

# Streamlit 실험 페이지
streamlit run logo_gen_exp/app_logo_lab.py
```

## 환경변수 의존

- `OPENAI_API_KEY` — 실제 생성
- `LANGFUSE_PUBLIC_KEY` / `LANGFUSE_SECRET_KEY` / `LANGFUSE_HOST` — trace (선택)
