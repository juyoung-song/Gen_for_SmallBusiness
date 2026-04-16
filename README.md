# Brewgram

소상공인 카페·베이커리·디저트 브랜드를 위한 모바일 우선 AI 광고 콘텐츠 생성 서비스입니다.

현재 기준 진입점은 `mobile_app.py` + Stitch 정적 UI입니다. 사용자는 `https://brewgram.duckdns.org`에 접속해 PWA처럼 사용하고, 브랜드 온보딩, 상품 기반 광고 생성, 인스타그램 피드/스토리 업로드까지 진행합니다.

## 현재 구조

```text
Mobile browser / PWA
  -> https://brewgram.duckdns.org
  -> Caddy (:80/:443)
  -> mobile_app.py (127.0.0.1:8011)
  -> SQLite/files (/srv/brewgram/data)
```

이미지 생성은 환경변수에 따라 두 방식 중 하나로 동작합니다.

```text
IMAGE_BACKEND_KIND=openai_image
  -> mobile_app.py가 OpenAI 이미지 API를 직접 호출
  -> worker_api.py 불필요

IMAGE_BACKEND_KIND=remote_worker
  -> mobile_app.py가 worker_api.py(127.0.0.1:8010)를 호출
  -> worker_api.py가 hf_local / hf_remote_api / mock 백엔드로 이미지 생성
```

현재 VM 데모에서는 `openai_image` 경로를 주로 사용합니다. `worker_api.py`는 로컬 diffusers/Hugging Face 워커 모드가 필요할 때만 띄웁니다.

## 주요 기능

- 브랜드 온보딩: 브랜드 이름, 색상, 분위기, 설명, 로고, 직접 업로드한 스크린샷을 기반으로 브랜드 분석 글을 생성합니다.
- 인스타 레퍼런스 캡처: VM IP가 Instagram 429에 막히는 경우를 피하기 위해 Mac 로컬 캡처 워커를 Cloudflare Tunnel로 연결할 수 있습니다.
- 상품 생성 플로우: 신상품 여부를 먼저 선택하고, 신상품이면 상품 사진을 업로드합니다. 기존 상품이면 DB에 저장된 기존 상품 이미지를 재사용합니다.
- 광고 생성: 텍스트만, 이미지만, 텍스트+이미지 생성을 지원합니다.
- 인스타 업로드: `.env`의 기본 업로드 계정 fallback을 모바일 업로드에서 사용하지 않습니다. 반드시 사용자가 OAuth로 연결한 Instagram professional account에만 게시합니다.
- Langfuse 추적: 브라우저별 익명 `client_id`와 세션 ID를 요청 헤더로 보내 모바일 생성·캡션·업로드 흐름을 추적합니다.

## 핵심 파일

```text
mobile_app.py                         # FastAPI 모바일/PWA 진입점
worker_api.py                         # 선택 사항: 내부 이미지 워커 API
scripts/instagram_capture_worker.py   # 선택 사항: Mac 로컬 Instagram 캡처 워커
stitch/                               # 모바일 정적 UI
services/                             # 생성/온보딩/인스타/OAuth 서비스
backends/                             # 이미지/텍스트 백엔드
models/                               # SQLAlchemy ORM
config/settings.py                    # 환경변수 설정
docs/mobile_worker_workflow.md        # 모바일 생성/관측 흐름
BREWGRAM_WORKER.md                    # VM 운영 가이드
infra/                                # Caddy/systemd/deploy 템플릿
```

## VM 운영 env

운영 env는 repo 밖에 둡니다.

```text
/etc/brewgram/mobile_app.env
/etc/brewgram/worker_api.env
/srv/brewgram/data/history.db
```

`/etc/brewgram/mobile_app.env` 핵심값:

```env
APP_ENV=production
LOG_LEVEL=INFO
APP_DATA_DIR=/srv/brewgram/data

OPENAI_API_KEY=...
TEXT_MODEL=gpt-5-mini
TEXT_TIMEOUT=90.0

IMAGE_BACKEND_KIND=openai_image
IMAGE_TIMEOUT=180.0

FREEIMAGE_API_KEY=...
META_APP_ID=...
META_APP_SECRET=...
TOKEN_ENCRYPTION_KEY=...
META_REDIRECT_URI_MOBILE=https://brewgram.duckdns.org/api/mobile/instagram/callback

LANGFUSE_PUBLIC_KEY=...
LANGFUSE_SECRET_KEY=...
LANGFUSE_HOST=https://us.cloud.langfuse.com/

# 선택: Mac 로컬 Instagram 캡처 워커
INSTAGRAM_CAPTURE_WORKER_URL=https://<cloudflare-tunnel>.trycloudflare.com
INSTAGRAM_CAPTURE_WORKER_TOKEN=...
INSTAGRAM_CAPTURE_WORKER_TIMEOUT=90.0
```

`remote_worker` 모드를 쓸 때만 추가:

```env
IMAGE_BACKEND_KIND=remote_worker
IMAGE_WORKER_URL=http://127.0.0.1:8010
IMAGE_WORKER_TOKEN=...
IMAGE_WORKER_TIMEOUT=180.0
```

`/etc/brewgram/worker_api.env`는 `remote_worker` 모드를 쓸 때만 필요합니다.

```env
APP_ENV=production
LOG_LEVEL=INFO
APP_DATA_DIR=/srv/brewgram/data

OPENAI_API_KEY=...
TEXT_MODEL=gpt-5-mini

IMAGE_BACKEND_KIND=hf_local
IMAGE_WORKER_HOST=127.0.0.1
IMAGE_WORKER_PORT=8010
IMAGE_WORKER_TOKEN=...
```

## VM 실행

수동으로 VM에서 실행:

```bash
cd ~/Gen_for_SmallBusiness
git fetch origin
git switch codex/oauth-only-mobile-upload
git pull --ff-only origin codex/oauth-only-mobile-upload
uv sync

set -a
source /etc/brewgram/mobile_app.env
set +a
uv run uvicorn mobile_app:app --host 127.0.0.1 --port 8011
```

systemd로 운영 중이면:

```bash
sudo systemctl restart brewgram-mobile.service
sudo systemctl status brewgram-mobile.service --no-pager
```

`remote_worker` 모드일 때만 worker도 함께 재시작합니다.

```bash
sudo systemctl restart brewgram-worker.service brewgram-mobile.service
```

## Mac Instagram 캡처 워커

Instagram이 GCP VM IP에서 429를 반환하면, Mac에서 로그인된 브라우저 세션으로 캡처하고 VM에는 이미지만 넘깁니다.

Mac 최초 로그인:

```bash
cd /Users/apple/Gen_for_SmallBusiness
CAPTURE_WORKER_TOKEN="<TOKEN>" \
CAPTURE_WORKER_HEADLESS=0 \
uv run python scripts/instagram_capture_worker.py login
```

Mac 캡처 워커 실행:

```bash
cd /Users/apple/Gen_for_SmallBusiness
CAPTURE_WORKER_TOKEN="<TOKEN>" \
CAPTURE_WORKER_HEADLESS=1 \
uv run uvicorn scripts.instagram_capture_worker:app --host 127.0.0.1 --port 8020
```

Cloudflare Tunnel:

```bash
cloudflared tunnel --url http://127.0.0.1:8020
```

Tunnel URL을 VM의 `/etc/brewgram/mobile_app.env`에 `INSTAGRAM_CAPTURE_WORKER_URL`로 넣고 `mobile_app.py`를 재시작합니다.

## OAuth 업로드 기준

모바일 업로드는 OAuth 연결된 계정만 사용합니다.

- `META_ACCESS_TOKEN` / `INSTAGRAM_ACCOUNT_ID`가 env에 있어도 모바일 업로드 fallback으로 쓰지 않습니다.
- 업로드 전 `brands.instagram_account_id`와 활성 `instagram_connections` 토큰이 필요합니다.
- OAuth 자동 후보 목록에 원하는 계정이 없으면, UI에서 Instagram `@username`을 입력해 후보 중 해당 계정을 선택합니다.
- 입력한 `@username`은 현재 Meta 로그인 계정이 접근 가능한 Facebook Page에 연결된 Instagram professional account 후보 안에서만 매칭됩니다.

Meta 앱의 Valid OAuth Redirect URIs에는 최소 아래 값을 넣습니다.

```text
https://brewgram.duckdns.org/api/mobile/instagram/callback
http://localhost:8501/
```

## 데이터 초기화

DB만 초기화:

```bash
pkill -f "uvicorn mobile_app:app" || true
cp /srv/brewgram/data/history.db /srv/brewgram/data/history.db.backup-$(date +%Y%m%d-%H%M%S) 2>/dev/null || true
rm -f /srv/brewgram/data/history.db
```

data 전체 초기화:

```bash
pkill -f "uvicorn mobile_app:app" || true
cp -a /srv/brewgram/data /srv/brewgram/data.backup-$(date +%Y%m%d-%H%M%S)
rm -rf /srv/brewgram/data
install -d /srv/brewgram/data
```

systemd 운영이면 `pkill` 대신 `sudo systemctl stop/start brewgram-mobile.service`를 사용합니다.

## 문서

- [BREWGRAM_WORKER.md](BREWGRAM_WORKER.md): VM 운영 절차
- [docs/mobile_worker_workflow.md](docs/mobile_worker_workflow.md): 생성/업로드/Langfuse 흐름
- [docs/onboarding.md](docs/onboarding.md): 온보딩과 Instagram 캡처 흐름
- [docs/schema.md](docs/schema.md): 현재 DB 스키마
- [docs/schema_migration.md](docs/schema_migration.md): 구 스키마에서 신 스키마로의 변경점

## 레거시 문서 주의

`VM_WORKER.md`, `VM_RESTART.md`, `docs/architecture.md`, `docs/PRD.md`, `docs/stack.md`, `docs/design.md`, `docs/generation.md`는 과거 Streamlit 또는 “Mac local app + VM worker” 기준 내용이 섞여 있습니다. 현재 운영 기준은 이 README, `BREWGRAM_WORKER.md`, `docs/mobile_worker_workflow.md`를 우선합니다.
