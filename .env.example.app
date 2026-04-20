# ════════════════════════════════════════════════════════════════
# .env.example.app
# 역할: Streamlit 프론트엔드 (사용자 Mac 또는 호스팅 서버)
# 사용 시나리오:
#   - 사용자 입력 받기 / UI 렌더링 / 인스타 게시
#   - 무거운 이미지 생성은 별도 VM 워커 또는 같은 머신에 위임
#
# 사용법:
#   cp .env.example.app .env
#   # 아래 <CHANGE_ME> 들을 실제 값으로 채우기
#   uv run streamlit run app.py
# ════════════════════════════════════════════════════════════════

# ── 앱 환경 ──
APP_ENV=development          # development | production
LOG_LEVEL=INFO               # DEBUG | INFO | WARNING | ERROR

# ── 이미지 생성 백엔드 (Stage 2 단일 enum) ──
# 가능한 값:
#   mock           — Pillow 그라데이션 (개발 중 UI 검증용, 외부 호출 0)
#   hf_local       — 같은 머신의 diffusers (Mac 에선 매우 느림)
#   hf_remote_api  — Hugging Face Serverless API (HUGGINGFACE_API_KEY 필요)
#   remote_worker  — 자체 GCP VM 워커 호출 (이 .env 의 기본 권장값)
#
# 개발 중에는 사이드바 dropdown 으로 즉시 전환 가능 (메모리만 — 재시작 시 .env 값으로 복귀)
IMAGE_BACKEND_KIND=remote_worker

# ── OpenAI (텍스트 생성 + Vision 분석 — 무조건 OpenAI) ──
OPENAI_API_KEY=<CHANGE_ME>
TEXT_MODEL=gpt-5-mini
TEXT_TIMEOUT=30.0

# ── Langfuse (선택: OpenAI 호출 trace 수집) ──
LANGFUSE_PUBLIC_KEY=
LANGFUSE_SECRET_KEY=
LANGFUSE_HOST=https://cloud.langfuse.com

# ── 원격 이미지 워커 (IMAGE_BACKEND_KIND=remote_worker 시 필수) ──
IMAGE_WORKER_URL=http://YOUR_VM_IP:8006/
IMAGE_WORKER_TOKEN=<CHANGE_ME_LONG_RANDOM>
IMAGE_WORKER_TIMEOUT=180.0

# ── Hugging Face API (IMAGE_BACKEND_KIND=hf_remote_api 시 필수) ──
# 위 IMAGE_BACKEND_KIND 가 hf_remote_api 가 아니면 비워둬도 됨
HUGGINGFACE_API_KEY=
IMAGE_MODEL=stabilityai/stable-diffusion-xl-base-1.0
IMAGE_TIMEOUT=60.0

# ── 인스타그램 자동 게시 (Meta Graph API + FreeImage) ──
META_ACCESS_TOKEN=<CHANGE_ME>
INSTAGRAM_ACCOUNT_ID=<CHANGE_ME>
FREEIMAGE_API_KEY=6d207e02198a847aa98d0a2a901485a5    # 공용 키 기본값, 변경 안 해도 됨

# ── 인스타그램 OAuth (사장님 계정 직접 연결) ──
# Streamlit 과 Stitch 모바일을 둘 다 쓸 경우 아래 2개 redirect URI 를 Meta 앱에 모두 등록
META_APP_ID=
META_APP_SECRET=
TOKEN_ENCRYPTION_KEY=
META_REDIRECT_URI_STREAMLIT=http://localhost:8501/
META_REDIRECT_URI_MOBILE=http://localhost:8007/api/mobile/instagram/callback
# legacy fallback (가능하면 비워두고 위 2개를 사용)
META_REDIRECT_URI=
