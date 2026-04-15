# `team1` VM 운영 가이드

이 문서는 현재 운영 중인 **단일 VM 배포 구조**를 기준으로 정리한 가이드다.

예전처럼 각 팀원이 맥 로컬에서 `mobile_app.py`를 띄우고 `SSH 터널`로 공용 워커에 붙는 방식이 아니다.
지금은 `team1` VM 안에서 `mobile_app.py`와 `worker_api.py`를 함께 띄우고,
외부 사용자는 `https://brewgram.duckdns.org`로 접속한다.

## 1. 현재 구조

```text
Internet
  -> Caddy (80/443, TLS 종료)
  -> mobile_app.py (127.0.0.1:8011)
  -> worker_api.py (127.0.0.1:8010)
  -> /srv/brewgram/data (SQLite + 업로드/생성 파일)
```

핵심 원칙:
- 외부 공개는 `mobile_app`만 한다.
- `worker_api`는 VM 내부 루프백(`127.0.0.1`)으로만 연다.
- `mobile_app`는 `IMAGE_BACKEND_KIND=remote_worker`로 내부 `worker_api`를 호출한다.
- 앱 데이터는 repo 밖 `/srv/brewgram/data`에 둬서 `git pull`이나 재배포와 분리한다.
- 운영 기준 브랜치는 현재 `merge/dev`다.

## 2. 현재 기준 값

- VM 이름: `team1`
- 공개 도메인: `brewgram.duckdns.org`
- `Caddy`: `:80`, `:443`
- `mobile_app`: `127.0.0.1:8011`
- `worker_api`: `127.0.0.1:8010`
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
- 내부 워커 호출 설정
- Meta OAuth / 업로드 / Langfuse / 앱 데이터 경로 설정

핵심 값:

```env
APP_DATA_DIR=/srv/brewgram/data
IMAGE_BACKEND_KIND=remote_worker
IMAGE_WORKER_URL=http://127.0.0.1:8010
IMAGE_WORKER_TOKEN=...
META_REDIRECT_URI_MOBILE=https://brewgram.duckdns.org/api/mobile/instagram/callback
```

### `/etc/brewgram/worker_api.env`

역할:
- 내부 이미지 워커 설정
- 로컬 HF/SD 이미지 생성 설정

핵심 값:

```env
APP_DATA_DIR=/srv/brewgram/data
IMAGE_BACKEND_KIND=hf_local
IMAGE_WORKER_HOST=127.0.0.1
IMAGE_WORKER_PORT=8010
IMAGE_WORKER_TOKEN=...
```

주의:
- `IMAGE_WORKER_TOKEN`은 두 env에서 같아야 한다.
- `TOKEN_ENCRYPTION_KEY`는 한 번 정하면 유지해야 한다.
- `APP_DATA_DIR=/srv/brewgram/data`가 빠지면 repo 내부 `data/`를 다시 쓰게 된다.

## 5. systemd 서비스

현재 운영 서비스 이름:
- `brewgram-mobile.service`
- `brewgram-worker.service`

둘 다 `enabled` 상태로 두고 VM 부팅 시 자동 시작되게 한다.

상태 확인:

```bash
sudo systemctl status brewgram-mobile.service --no-pager
sudo systemctl status brewgram-worker.service --no-pager
```

재시작:

```bash
sudo systemctl restart brewgram-worker.service brewgram-mobile.service
```

service 파일을 수정했을 때만 먼저:

```bash
sudo systemctl daemon-reload
```

## 6. 수동 배포 절차

자동배포가 불안정하거나 아직 안 붙어 있으면, 아래 명령으로 수동 배포한다.

실행 위치: `VM SSH`

```bash
cd ~/Gen_for_SmallBusiness
git fetch origin
git switch merge/dev
git pull --ff-only origin merge/dev
uv sync
uv run python -m playwright install chromium
sudo systemctl daemon-reload
sudo systemctl restart brewgram-worker.service brewgram-mobile.service
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
- 두 서비스가 `active (running)`
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

## 10. GitHub Actions 자동배포

현재 repo에는 아래 흐름의 자동배포가 들어가 있다.

```text
push to merge/dev
  -> GitHub Actions
  -> SSH to VM
  -> /usr/local/bin/deploy-brewgram.sh
  -> git pull --ff-only
  -> uv sync
  -> playwright install chromium
  -> systemd restart
```

주의:
- `deploy-brewgram.sh`는 `uv sync` 후 Playwright 브라우저 바이너리(`chromium`)를 설치한다.
- OS 패키지 설치가 필요한 `playwright install-deps chromium`은 `sudo apt`를 건드리므로 자동배포에 넣지 않는다. VM 최초 세팅 때만 수동 실행한다.

필요 secret:
- `VM_HOST`
- `VM_USER`
- `VM_SSH_KEY`

워크플로 파일:
- `.github/workflows/deploy-infra.yml`

주의:
- 현재 저장소가 개인 저장소면 `production` environment secret 수정은 owner가 해야 할 수 있다.
- 자동배포가 실패하면 수동 배포 절차를 기준으로 운영하면 된다.

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
