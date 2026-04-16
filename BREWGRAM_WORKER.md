# `team1` VM 운영 가이드

이 문서는 현재 운영 중인 **단일 VM 배포 구조**를 기준으로 정리한 가이드다.

예전처럼 각 팀원이 맥 로컬에서 `mobile_app.py`를 띄우고 `SSH 터널`로 공용 워커에 붙는 방식이 아니다.
지금은 `team1` VM 안에서 `mobile_app.py`를 띄우고, 외부 사용자는 `https://brewgram.duckdns.org`로 접속한다.

이미지 생성은 두 모드를 구분한다.

- `IMAGE_BACKEND_KIND=openai_image`: `mobile_app.py`가 OpenAI 이미지 API를 직접 호출한다. `worker_api.py`는 필요 없다.
- `IMAGE_BACKEND_KIND=remote_worker`: `mobile_app.py`가 VM 내부 `worker_api.py`를 호출한다. 이때만 `worker_api.py`를 함께 띄운다.

## 1. 현재 구조

```text
Internet
  -> Caddy (80/443, TLS 종료)
  -> mobile_app.py (127.0.0.1:8011)
  -> [optional] worker_api.py (127.0.0.1:8010, remote_worker 모드)
  -> /srv/brewgram/data (SQLite + 업로드/생성 파일)
```

핵심 원칙:
- 외부 공개는 `mobile_app`만 한다.
- `worker_api`를 쓸 경우 VM 내부 루프백(`127.0.0.1`)으로만 연다.
- `openai_image` 모드에서는 `worker_api`를 띄우지 않아도 된다.
- `remote_worker` 모드에서는 `mobile_app`가 내부 `worker_api`를 호출한다.
- 앱 데이터는 repo 밖 `/srv/brewgram/data`에 둬서 `git pull`이나 재배포와 분리한다.
- 운영 기준 브랜치는 배포 시점에 명시한다. 현재 테스트 브랜치는 `codex/oauth-only-mobile-upload`다.

## 2. 현재 기준 값

- VM 이름: `team1`
- 공개 도메인: `brewgram.duckdns.org`
- `Caddy`: `:80`, `:443`
- `mobile_app`: `127.0.0.1:8011`
- `worker_api`: `127.0.0.1:8010` (remote_worker 모드에서만)
- 앱 데이터 루트: `/srv/brewgram/data`
- DB 파일: `/srv/brewgram/data/history.db`

## 3. 주요 파일 위치

```text
/home/spai0608/Gen_for_SmallBusiness
/srv/brewgram/data
/etc/brewgram/mobile_app.env
/etc/brewgram/worker_api.env
/etc/caddy/Caddyfile
/etc/systemd/system/brewgram-mobile.service
/etc/systemd/system/brewgram-worker.service
/usr/local/bin/deploy-brewgram.sh
```

## 4. env 역할

### `/etc/brewgram/mobile_app.env`

역할:
- 외부에서 받는 FastAPI 앱 설정
- 이미지 생성 백엔드 설정
- Meta OAuth / 업로드 / Langfuse / 앱 데이터 경로 설정

핵심 값:

```env
APP_DATA_DIR=/srv/brewgram/data
IMAGE_BACKEND_KIND=openai_image
META_REDIRECT_URI_MOBILE=https://brewgram.duckdns.org/api/mobile/instagram/callback
```

Mac 로컬 캡처 워커를 붙일 때 추가:

```env
INSTAGRAM_CAPTURE_WORKER_URL=https://<cloudflare-tunnel>.trycloudflare.com
INSTAGRAM_CAPTURE_WORKER_TOKEN=...
INSTAGRAM_CAPTURE_WORKER_TIMEOUT=90.0
```

`remote_worker` 모드를 쓸 때만 추가:

```env
IMAGE_BACKEND_KIND=remote_worker
IMAGE_WORKER_URL=http://127.0.0.1:8010
IMAGE_WORKER_TOKEN=...
```

### `/etc/brewgram/worker_api.env`

역할:
- 내부 이미지 워커 설정
- 로컬 HF/SD 이미지 생성 설정
- `IMAGE_BACKEND_KIND=remote_worker`일 때만 필요

핵심 값:

```env
APP_DATA_DIR=/srv/brewgram/data
IMAGE_BACKEND_KIND=hf_local
IMAGE_WORKER_HOST=127.0.0.1
IMAGE_WORKER_PORT=8010
IMAGE_WORKER_TOKEN=...
```

주의:
- `IMAGE_WORKER_TOKEN`은 `remote_worker` 모드에서 두 env가 같아야 한다.
- `TOKEN_ENCRYPTION_KEY`는 한 번 정하면 유지해야 한다.
- `APP_DATA_DIR=/srv/brewgram/data`가 빠지면 repo 내부 `data/`를 다시 쓰게 된다.

## 5. systemd 서비스

systemd 운영 서비스 이름:
- `brewgram-mobile.service`
- `brewgram-worker.service` (`remote_worker` 모드에서만 필수)

둘 다 `enabled` 상태로 두고 VM 부팅 시 자동 시작되게 한다.

상태 확인:

```bash
sudo systemctl status brewgram-mobile.service --no-pager
sudo systemctl status brewgram-worker.service --no-pager
```

재시작:

```bash
sudo systemctl restart brewgram-mobile.service
```

`remote_worker` 모드일 때:

```bash
sudo systemctl restart brewgram-worker.service brewgram-mobile.service
```

service 파일을 수정했을 때만 먼저:

```bash
sudo systemctl daemon-reload
```

## 6. 수동 배포 절차

아래 명령으로 VM에 수동 배포한다.

실행 위치: `VM SSH`

```bash
cd ~/Gen_for_SmallBusiness
git fetch origin
git switch codex/oauth-only-mobile-upload
git pull --ff-only origin codex/oauth-only-mobile-upload
uv sync
uv run python -m playwright install chromium
sudo systemctl daemon-reload
sudo systemctl restart brewgram-mobile.service
```

VM에 Chromium 런타임 패키지가 한 번도 설치되지 않았다면 아래 명령도 1회 실행한다.

```bash
sudo env PATH="$PATH" /home/spai0608/.local/bin/uv run python -m playwright install-deps chromium
```

배포 확인:

```bash
git rev-parse --short HEAD
sudo systemctl status brewgram-worker.service --no-pager
sudo systemctl status brewgram-mobile.service --no-pager
curl -I https://brewgram.duckdns.org/stitch/manifest.webmanifest
```

정상 기준:
- `git rev-parse --short HEAD`가 방금 push한 커밋과 같음
- 필요한 서비스가 `active (running)`. `openai_image` 모드에서는 mobile만 필수
- `manifest.webmanifest`가 `200 OK`

## 7. 외부 접속과 PWA

외부 사용자는 아래 주소로 접속한다.

```text
https://brewgram.duckdns.org
```

현재 조건:
- HTTPS 정상
- `manifest.webmanifest` 제공
- `service-worker.js` 제공
- iPhone Safari에서는 사용자가 `홈 화면에 추가`를 직접 눌러야 한다

점검:

```bash
curl -I https://brewgram.duckdns.org/
curl -I https://brewgram.duckdns.org/stitch/manifest.webmanifest
curl -I https://brewgram.duckdns.org/stitch/service-worker.js
```

## 8. 데이터 저장 위치와 초기화

현재 운영 데이터는 전부 `/srv/brewgram/data` 아래에 저장된다.

예:
- DB: `/srv/brewgram/data/history.db`
- 온보딩 파일: `/srv/brewgram/data/onboarding/mobile/`
- staging: `/srv/brewgram/data/staging/`
- 생성/브랜드 자산: `/srv/brewgram/data/...`

### DB만 초기화

```bash
sudo systemctl stop brewgram-mobile.service brewgram-worker.service
sudo cp /srv/brewgram/data/history.db /srv/brewgram/data/history.db.backup-$(date +%Y%m%d-%H%M%S)
sudo rm /srv/brewgram/data/history.db
sudo systemctl start brewgram-worker.service brewgram-mobile.service
```

### data 전체 초기화

```bash
sudo systemctl stop brewgram-mobile.service brewgram-worker.service
sudo cp -a /srv/brewgram/data /srv/brewgram/data.backup-$(date +%Y%m%d-%H%M%S)
sudo rm -rf /srv/brewgram/data
sudo install -d -o spai0608 -g spai0608 /srv/brewgram/data
sudo systemctl start brewgram-worker.service brewgram-mobile.service
```

## 9. Meta OAuth 운영 기준

운영 redirect URI는 아래 값이 맞다.

```text
https://brewgram.duckdns.org/api/mobile/instagram/callback
```

Meta 앱의 `Valid OAuth Redirect URIs`에는 최소 아래 둘을 유지하는 편이 좋다.
- `http://localhost:8501/`
- `https://brewgram.duckdns.org/api/mobile/instagram/callback`

주의:
- `http://brewgram.duckdns.org`는 현재 코드 기준으로 맞지 않는다.
- 루트 도메인이 아니라 callback path까지 정확히 등록돼야 한다.
- 모바일 업로드는 `.env`의 `META_ACCESS_TOKEN` fallback을 쓰지 않는다. 사용자가 OAuth로 직접 연결한 계정만 업로드 가능하다.
- 수동 연결 UI는 숫자 ID가 아니라 Instagram `@username`을 받는다. 단, 현재 Meta 로그인 계정이 접근 가능한 Page 후보 안에서만 매칭된다.

## 9.1 Mac Instagram 캡처 워커

GCP VM IP가 Instagram에서 429를 받으면, Mac의 로그인된 브라우저 세션으로 캡처하고 VM에는 이미지만 반환한다.

Mac 최초 로그인:

```bash
cd /Users/apple/Gen_for_SmallBusiness
CAPTURE_WORKER_TOKEN="<TOKEN>" \
CAPTURE_WORKER_HEADLESS=0 \
uv run python scripts/instagram_capture_worker.py login
```

Mac 워커 실행:

```bash
CAPTURE_WORKER_TOKEN="<TOKEN>" \
CAPTURE_WORKER_HEADLESS=1 \
uv run uvicorn scripts.instagram_capture_worker:app --host 127.0.0.1 --port 8020
```

Cloudflare Tunnel:

```bash
cloudflared tunnel --url http://127.0.0.1:8020
```

VM `/etc/brewgram/mobile_app.env`:

```env
INSTAGRAM_CAPTURE_WORKER_URL=https://<cloudflare-tunnel>.trycloudflare.com
INSTAGRAM_CAPTURE_WORKER_TOKEN=<TOKEN>
INSTAGRAM_CAPTURE_WORKER_TIMEOUT=90.0
```

## 10. 배포 운영 기준

현재 repo에서는 GitHub Actions 자동배포를 사용하지 않는다.
VM 반영은 6번의 수동 배포 절차를 기준으로 한다.

주의:
- `/usr/local/bin/deploy-brewgram.sh`는 VM에 남겨둘 수 있다. 필요하면 VM SSH에서 직접 실행한다.
- 예: `BREWGRAM_DEPLOY_BRANCH=codex/oauth-only-mobile-upload deploy-brewgram.sh`
- 브랜치를 바꿀 때는 `BREWGRAM_DEPLOY_BRANCH` 값만 바꾼다.
- `deploy-brewgram.sh`는 `uv sync` 후 Playwright 브라우저 바이너리(`chromium`)를 설치한다.
- OS 패키지 설치가 필요한 `playwright install-deps chromium`은 `sudo apt`를 건드리므로 VM 최초 세팅 때만 수동 실행한다.
- VM 작업 트리에 수동 수정이 남아 있으면 `git pull --ff-only`가 실패할 수 있다.

## 11. 자주 보는 확인 명령

### 포트 리슨 상태

```bash
ss -ltnp | egrep '8010|8011|:80|:443'
```

정상 예시:
- `127.0.0.1:8010` -> worker
- `127.0.0.1:8011` -> mobile
- `:80`, `:443` -> caddy

### 내부 health

```bash
curl http://127.0.0.1:8010/health
curl http://127.0.0.1:8011/health
```

### 서비스 로그

```bash
sudo journalctl -u brewgram-worker.service -n 100 --no-pager
sudo journalctl -u brewgram-mobile.service -n 100 --no-pager
sudo journalctl -u caddy -n 100 --no-pager
```

## 12. 이 문서에서 버린 예전 방식

더 이상 현재 기준 문서로 보지 않는 항목:
- 맥 로컬에서 `mobile_app.py`를 띄우는 기본 운영 방식
- `SSH -L` 터널로 공용 워커에 붙는 방식
- `8005`, `8008` 기준 포트 문서
- `team1` VM을 “워커만” 쓰는 구조

즉 지금은 **공용 VM 단일 배포 문서**로 이해하면 된다.
