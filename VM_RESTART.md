# VM / Mac Restart Guide

이 문서는 `team1` VM 워커와 맥 로컬 `mobile_app.py`를 다시 띄우는 절차를 빠르게 정리한 운영 메모다.

기본 구조:

- VM 워커: `worker_api.py` on `127.0.0.1:8005`
- 맥 SSH 터널: `127.0.0.1:18005 -> VM 127.0.0.1:8005`
- 맥 로컬 앱: `mobile_app.py` on `127.0.0.1:8008`

권장 접속 방식:

- `plain ssh` 대신 `gcloud compute ssh` 사용
- 이유: 로컬 `~/.ssh/id_ed25519` 직접 인증이 불안정했고, `gcloud` 경로가 더 안정적이었음

## 1. 항상 열어둬야 하는 터미널

닫으면 안 되는 터미널:

- 맥 터미널 A: SSH 터널
- 맥 터미널 B: 로컬 `mobile_app.py`

닫아도 되는 터미널:

- VM SSH 셸
- 이유: 워커는 `nohup` 백그라운드로 띄우기 때문

## 2. 가장 자주 쓰는 상태 확인

### VM 워커 상태 확인

실행 위치: `VM SSH`

```bash
pgrep -af "uvicorn worker_api:app"
tail -n 50 ~/worker_api.log
curl http://127.0.0.1:8005/health
```

### 맥 터널 상태 확인

실행 위치: `맥 터미널`

```bash
curl http://127.0.0.1:18005/health
```

### 맥 로컬 앱 상태 확인

실행 위치: `맥 터미널`

```bash
curl http://127.0.0.1:8008/health
curl http://127.0.0.1:8008/api/mobile/bootstrap
```

## 3. VM 워커 실행 / 재실행

### 3-1. VM 최신 코드 받고 워커 재실행

실행 위치: `VM SSH`

```bash
cd ~/Gen_for_SmallBusiness
git fetch origin
git switch <worker-branch>
git pull --ff-only
uv sync --no-dev
pkill -f "uvicorn worker_api:app --host 127.0.0.1 --port 8005"
nohup /home/apple/.local/bin/uv run uvicorn worker_api:app --host 127.0.0.1 --port 8005 > ~/worker_api.log 2>&1 &
sleep 2
tail -n 30 ~/worker_api.log
curl http://127.0.0.1:8005/health
```

주의:

- VM 유저명이 `apple`이 아니면 `nohup` 명령의 경로를 실제 `which uv` 결과로 바꿔야 한다.
- 처음 1회는 경로 확인:

```bash
which uv
```

예:

```bash
/home/apple/.local/bin/uv
```

### 3-2. 워커 로그 실시간 보기

실행 위치: `VM SSH`

```bash
tail -f ~/worker_api.log
```

빠져나오기:

```text
Ctrl+C
```

### 3-3. 워커 토큰 확인

실행 위치: `VM SSH`

```bash
cd ~/Gen_for_SmallBusiness
rg -n "^IMAGE_WORKER_TOKEN=" .env
printenv IMAGE_WORKER_TOKEN
```

맥 로컬 `mobile_app.py`에서 사용하는 `IMAGE_WORKER_TOKEN` 값과 반드시 같아야 한다.

## 4. 맥 SSH 터널 실행 / 재실행

### 4-1. 터널 열기

실행 위치: `맥 터미널 A`

```bash
gcloud compute ssh team1 --zone us-central1-c -- -N -L 18005:127.0.0.1:8005
```

정상 동작:

- 출력 없이 멈춰 있음
- 이 창을 닫으면 터널 종료

### 4-2. 터널 확인

실행 위치: `맥 터미널`

```bash
curl http://127.0.0.1:18005/health
```

### 4-3. 터널 재실행이 필요한 경우

- 터널 창을 닫았을 때
- `gcloud compute ssh ... -N -L ...` 창이 끊겼을 때
- `curl http://127.0.0.1:18005/health` 가 실패할 때

재실행 필요 없는 경우:

- VM 워커만 재시작했을 때
- 로컬 `mobile_app.py`만 재시작했을 때

즉, 터널 프로세스가 살아 있으면 보통 다시 열 필요 없다.

## 5. 맥 로컬 mobile_app 실행 / 재실행

### 5-1. 로컬 코드 최신 반영 후 앱 재실행

실행 위치: `맥 터미널 B`

```bash
cd /Users/apple/Gen_for_SmallBusiness
git fetch origin
git switch <ui-branch>
git pull --ff-only
lsof -iTCP:8008 -sTCP:LISTEN
kill <PID>
set -a
source .env
set +a
export IMAGE_BACKEND_KIND=remote_worker
export IMAGE_WORKER_URL=http://127.0.0.1:18005
export IMAGE_WORKER_TOKEN=<VM과 같은 토큰>
export IMAGE_WORKER_TIMEOUT=360
export TEXT_TIMEOUT=90
uv run uvicorn mobile_app:app --host 127.0.0.1 --port 8008
```

포트 8008에 프로세스가 없으면 `kill <PID>` 는 생략한다.

### 5-2. 브라우저 확인

실행 위치: `브라우저`

```text
http://127.0.0.1:8008/
http://127.0.0.1:8008/stitch/welcome.html
http://127.0.0.1:8008/stitch/2./code.html
```

## 6. 언제 무엇을 재실행해야 하나

### A. VM 워커만 재실행하면 되는 경우

다음이 바뀌면 VM 워커 재실행:

- VM의 `.env` 값 변경
- `OPENAI_API_KEY`, `IMAGE_WORKER_TOKEN` 등 워커가 읽는 환경변수 변경
- `worker_api.py`
- `services/image_service.py`
- `backends/*`
- 워커가 직접 import 하는 backend/service 코드

보통 필요한 작업:

1. VM에서 `git pull --ff-only`
2. VM 워커 재시작

터널은 보통 그대로 둔다.

### B. 맥 로컬 앱만 재실행하면 되는 경우

다음이 바뀌면 맥 로컬 `mobile_app.py` 재실행:

- `mobile_app.py`
- `stitch/*`
- `stitch/shared.js`
- `stitch/shared.css`
- `stitch/*.html`
- 로컬 UI/프런트엔드 동작만 바뀐 경우

보통 필요한 작업:

1. 맥에서 `git pull --ff-only`
2. 포트 8008 프로세스 종료
3. `mobile_app.py` 재실행

VM 워커는 그대로 둔다.

### C. 둘 다 재실행해야 하는 경우

다음 상황이면 둘 다 재실행:

- backend + UI를 같이 수정한 브랜치 업데이트
- 어떤 파일이 워커 쪽인지 애매할 때
- `refactor/flow` 계열 backend 변경과 Stitch UI 변경을 함께 받았을 때
- 원인 분리보다 빨리 새 상태를 맞추는 것이 중요할 때

가장 안전한 순서:

1. VM에서 `git pull --ff-only`
2. VM 워커 재시작
3. 맥에서 `git pull --ff-only`
4. 맥 로컬 앱 재시작
5. 헬스체크

### D. 터널만 다시 열면 되는 경우

- `gcloud compute ssh ... -N -L ...` 창을 닫았을 때
- 맥이 잠자기 후 터널이 끊겼을 때
- `curl http://127.0.0.1:18005/health` 만 실패하고, VM `8005`는 살아 있을 때

이 경우:

1. VM 워커는 건드리지 않음
2. 터널만 다시 열기

## 7. 빠른 복구 순서

문제가 났고 어디가 죽었는지 확신이 없을 때:

### 7-1. VM 워커 확인

실행 위치: `VM SSH`

```bash
curl http://127.0.0.1:8005/health
tail -n 30 ~/worker_api.log
```

### 7-2. 터널 확인

실행 위치: `맥 터미널`

```bash
curl http://127.0.0.1:18005/health
```

### 7-3. 로컬 앱 확인

실행 위치: `맥 터미널`

```bash
curl http://127.0.0.1:8008/health
```

### 7-4. 그래도 애매하면 전부 새로 맞추기

1. VM 워커 재시작
2. 맥 터널 재오픈
3. 맥 로컬 앱 재시작

## 8. VSCode 관련 참고

- `stitch` UI는 정적 파일 미리보기가 아니라 `mobile_app.py`를 통해 봐야 한다.
- VSCode에서 보고 싶으면 파일 preview 대신 실행 중인 URL을 VSCode `Simple Browser`로 연다.
- `.db`, `.png` 미리보기에서 `service worker` 에러가 나면 VSCode webview 캐시 문제일 수 있다.
- 이 경우 아래 경로를 삭제하면 복구된 사례가 있었다:

```text
/Users/apple/Library/Application Support/Code/Service Worker
```
