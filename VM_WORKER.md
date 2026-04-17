# Shared `team1` VM Worker Guide

> Legacy note: 이 문서는 예전 “각 팀원이 Mac 로컬에서 `mobile_app.py`를 실행하고 VM worker를 SSH 터널로 공유”하던 구조를 설명한다.
> 현재 운영 기준은 [BREWGRAM_WORKER.md](BREWGRAM_WORKER.md)와 [README.md](README.md)를 우선한다.
> 현재 `openai_image` 모드에서는 `worker_api.py` 공유가 필요 없을 수 있다.

이 문서는 **이미 만들어진 공용 GCP VM `team1`** 을 이미지 워커로 사용하고,
각 팀원이 **자기 로컬 브랜치에서** `mobile_app.py` 와 Stitch UI를 실행하는 방법을 정리한 가이드다.

핵심 원칙:
- 워커는 **VM `team1`에서 한 번만 실행**한다.
- 각 팀원은 **자기 맥 로컬 브랜치**에서 `mobile_app.py` 를 실행한다.
- 각 팀원은 자기 로컬에서 **SSH 터널만** 열어 공용 VM 워커에 붙는다.
- 로컬 브랜치가 달라도 `mobile_app.py -> worker_api.py` API 계약이 같으면 같이 쓸 수 있다.
- `worker_api.py`, `config/settings.py`, `services/image_service.py` 계약이 바뀌는 브랜치라면, VM 워커 브랜치도 함께 맞춰야 한다.

## 실행 위치 표기

- `맥 터미널`: 로컬 macOS Terminal/iTerm
- `GCP 콘솔 SSH`: GCP 웹 콘솔에서 `VM instances > team1 > SSH`
- `VM SSH`: 맥에서 `ssh user@ip`로 직접 접속한 `team1` 셸
- `맥 브라우저`: 로컬 브라우저

## 현재 기준 값

- 공용 VM 이름: `team1`
- 공용 VM 외부 IP: `<TEAM1_VM_EXTERNAL_IP>`
- VM 워커 포트: `8005`
- 로컬 SSH 터널 포트 예시: `18005`
- 로컬 `mobile_app.py` 포트: `8008`

주의:
- 비밀값(`IMAGE_WORKER_TOKEN`, `OPENAI_API_KEY`)은 문서에 직접 넣지 말고 각자 `.env`에서 사용한다.
- 현재 코드에서 이미지 백엔드는 `IMAGE_BACKEND_KIND`로 결정된다.
- legacy 키인 `USE_MOCK`, `USE_LOCAL_MODEL`만 바꿔서는 동작이 바뀌지 않을 수 있다.

## 전체 구조

```text
Stitch UI (맥 브라우저)
  -> mobile_app.py (맥 로컬 브랜치)
  -> SSH tunnel (맥 127.0.0.1:<LOCAL_TUNNEL_PORT> -> team1 127.0.0.1:8005)
  -> worker_api.py (team1 VM)
  -> hf_local image backend (team1 VM)
```

## A. 관리자용: `team1` 워커 1회 세팅

이 섹션은 `team1` VM에 워커를 처음 올리거나, VM 워커 브랜치를 갱신할 때만 필요하다.

### A-1. `team1` Linux 사용자 확인

실행 위치: `GCP 콘솔 SSH`

```bash
whoami
```

예:

```bash
spai0000
```

### A-2. 맥 공개키를 `team1`에 등록

먼저 맥 공개키를 확인한다.

실행 위치: `맥 터미널`

먼저 사용할 공개키 파일을 확인한다. `~/.ssh/id_ed25519.pub`는 흔한 기본값이지만,
팀원마다 다를 수 있다.

```bash
ls ~/.ssh/*.pub
```

공개키가 하나도 없으면 새로 생성한다.

```bash
ssh-keygen -t ed25519 -C "<your-email-or-name>"
ls ~/.ssh/*.pub
```

그다음 사용할 공개키 파일을 출력한다.

```bash
cat <SSH_PUBLIC_KEY_PATH>
```

예:

```text
ssh-ed25519 AAAAC3Nz....... your_name@your-domain
```

이제 `team1`에 등록한다.

실행 위치: `GCP 콘솔 SSH`

```bash
mkdir -p ~/.ssh
chmod 700 ~/.ssh
printf '%s\n' 'ssh-ed25519 AAAAC3Nz....... your_name@your-domain' >> ~/.ssh/authorized_keys
chmod 600 ~/.ssh/authorized_keys
chmod go-w ~
tail -n 5 ~/.ssh/authorized_keys
```

### A-3. 맥에서 `team1` 직접 SSH 확인

실행 위치: `맥 터미널`

```bash
ssh -i <SSH_PRIVATE_KEY_PATH> <TEAM1_LINUX_USER>@<TEAM1_VM_EXTERNAL_IP>
```

예:

```bash
ssh -i ~/.ssh/id_ed25519 <TEAM1_LINUX_USER>@<TEAM1_VM_EXTERNAL_IP>
```

### A-4. `team1`에 저장소 clone 및 브랜치 맞추기

실행 위치: `VM SSH` 또는 `GCP 콘솔 SSH`

```bash
cd ~
git clone https://github.com/<repo-owner>/<repo-name>.git
cd Gen_for_SmallBusiness
git fetch origin
git switch <worker-branch>
git branch --show-current
git rev-parse --short HEAD
```

예:

```bash
git switch 브런치명
```

주의:
- 공용 워커 VM은 반드시 **현재 로컬 앱들과 호환되는 브랜치**로 맞춘다.

### A-5. `team1` `.env` 작성

실행 위치: `VM SSH` 또는 `GCP 콘솔 SSH`

워커 VM은 `hf_local` 모드여야 한다.

최소 예시:

```env
APP_ENV=production
LOG_LEVEL=INFO

OPENAI_API_KEY=<your-openai-key>
HUGGINGFACE_API_KEY=<optional-if-needed>

IMAGE_BACKEND_KIND=hf_local

IMAGE_WORKER_TOKEN=<shared-worker-token>
IMAGE_WORKER_HOST=0.0.0.0
IMAGE_WORKER_PORT=8005
IMAGE_WORKER_TIMEOUT=360

TEXT_MODEL=gpt-5-mini
TEXT_TIMEOUT=90
IMAGE_TIMEOUT=180

LOCAL_MODEL_CACHE_DIR=./models/cache
LOCAL_SD15_MODEL_ID=runwayml/stable-diffusion-v1-5
LOCAL_BACKEND=ip_adapter
LOCAL_INFERENCE_STEPS=18
LOCAL_GUIDANCE_SCALE=7.5
LOCAL_IP_ADAPTER_SCALE=0.6
LOCAL_IMG2IMG_STRENGTH=0.45
LOCAL_IP_ADAPTER_ID=h94/IP-Adapter
LOCAL_IP_ADAPTER_SUBFOLDER=models
LOCAL_IP_ADAPTER_WEIGHT_NAME=ip-adapter_sd15.bin
LOCAL_REFERENCE_MIN_SIDE=768
LOCAL_REFERENCE_SHARPEN_FACTOR=1.15
LOCAL_REFERENCE_CONTRAST_FACTOR=1.03
```

주의:
- `IMAGE_BACKEND_KIND=hf_local` 이 빠지면 `/health`가 `mock`으로 뜰 수 있다.

### A-6. `team1`에 `uv` 설치 및 의존성 설치

실행 위치: `VM SSH` 또는 `GCP 콘솔 SSH`

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
source "$HOME/.local/bin/env" || export PATH="$HOME/.local/bin:$PATH"
uv --version
cd ~/Gen_for_SmallBusiness
uv sync --no-dev
```

### A-7. `team1`에서 워커 실행

실행 위치: `VM SSH`

```bash
cd ~/Gen_for_SmallBusiness
uv run uvicorn worker_api:app --host 127.0.0.1 --port 8005
```

이 창은 계속 켜둔다.

### A-8. 관리자용 worker health 확인

실행 위치: `맥 터미널`

먼저 터널을 연다.

```bash
ssh -N -L <LOCAL_TUNNEL_PORT>:127.0.0.1:8005 -i <SSH_PRIVATE_KEY_PATH> <TEAM1_LINUX_USER>@<TEAM1_VM_EXTERNAL_IP>
```

그다음 다른 맥 터미널에서:

```bash
curl http://127.0.0.1:<LOCAL_TUNNEL_PORT>/health
```

정상 예시:

```json
{"ok":true,"image_backend_kind":"hf_local","image_model":"stabilityai/stable-diffusion-xl-base-1.0","local_backend":"ip_adapter"}
```

이제부터 팀원은 아래 B 섹션만 따라 하면 된다.

## B. 팀원용: 각자 로컬 브랜치에서 공용 `team1` 워커 사용

이 섹션은 **각 팀원이 자기 맥에서** 따라 하는 루틴이다.

전제:
- `team1` 워커가 이미 실행 중이다.
- `team1`의 `/health`가 `hf_local`로 정상 응답한다.

### B-1. 로컬 브랜치 준비

실행 위치: `맥 터미널`

```bash
cd <LOCAL_REPO_PATH>
git branch --show-current
git status --short
```

자기 작업 브랜치로 이동:

```bash
git switch <my-local-branch>
```

주의:
- 각자 자기 로컬 브랜치에서 `mobile_app.py`를 띄우면 된다.
- 다만 VM 워커 API 계약과 호환되지 않는 브랜치면, `team1` 워커 브랜치도 같이 맞춰야 한다.

### B-2. `team1`으로 SSH 터널 열기

실행 위치: `맥 터미널`

```bash
ssh -N -L <LOCAL_TUNNEL_PORT>:127.0.0.1:8005 -i <SSH_PRIVATE_KEY_PATH> <TEAM1_LINUX_USER>@<TEAM1_VM_EXTERNAL_IP>
```

예:

```bash
ssh -N -L 18005:127.0.0.1:8005 -i <SSH_PRIVATE_KEY_PATH> <TEAM1_LINUX_USER>@<TEAM1_VM_EXTERNAL_IP>
```

이 창은 출력 없이 멈춰 있는 것이 정상이다.
이 창을 닫으면 터널이 끊긴다.

### B-3. 로컬에서 `team1` 워커 health 확인

실행 위치: `맥 터미널`

```bash
curl http://127.0.0.1:<LOCAL_TUNNEL_PORT>/health
```

정상 예시:

```json
{"ok":true,"image_backend_kind":"hf_local","image_model":"stabilityai/stable-diffusion-xl-base-1.0","local_backend":"ip_adapter"}
```

### B-4. 로컬 `mobile_app.py` 실행

실행 위치: `맥 터미널`

기존 8008 포트가 이미 사용 중이면 먼저 종료:

```bash
lsof -iTCP:8008 -sTCP:LISTEN
kill <PID>
```

그 다음 실행:

```bash
cd <LOCAL_REPO_PATH>
set -a
source .env
set +a
export IMAGE_BACKEND_KIND=remote_worker
export IMAGE_WORKER_URL=http://127.0.0.1:<LOCAL_TUNNEL_PORT>
export IMAGE_WORKER_TOKEN=<shared-worker-token>
export IMAGE_WORKER_TIMEOUT=360
export TEXT_TIMEOUT=90
uv run uvicorn mobile_app:app --host 127.0.0.1 --port 8008
```

주의:
- 이 단계는 **자기 로컬 브랜치에서** 실행한다.
- `.env`의 다른 값은 각자 로컬 환경을 따른다.
- 단, 위 `export` 값은 공용 VM 워커를 보게 하는 override다.

### B-5. 로컬 bootstrap 확인

실행 위치: `맥 터미널`

```bash
curl http://127.0.0.1:8008/api/mobile/bootstrap
```

정상 예시:

```json
{"ok":true,"image_backend_kind":"remote_worker"}
```

### B-6. Stitch UI 검증

실행 위치: `맥 브라우저`

접속:

```text
http://127.0.0.1:8008/
```

검증 순서:
1. 먼저 `이미지만`으로 생성 테스트
2. 이미지 생성 성공 확인
3. 그 다음 `글+이미지` 테스트
4. 필요하면 캡션/스토리까지 확인

로그는 아래 두 곳을 같이 본다.
- `맥 터미널`: 로컬 `mobile_app.py`
- `VM SSH`: 공용 `worker_api.py`

## C. 브랜치 계약이 바뀔 때

다음 파일들 중 하나라도 바뀌면, 로컬 브랜치만 바꾸는 것으로는 부족할 수 있다.

- `worker_api.py`
- `config/settings.py`
- `services/image_service.py`
- `backends/*`
- `schemas/image_schema.py`

이 경우:
1. 로컬 브랜치를 push
2. `team1` VM repo도 같은 호환 브랜치/커밋으로 맞춤
3. `team1` 워커 재시작
4. 각 팀원은 다시 터널 + 로컬 앱 재실행

## D. 현재 구조에서 반드시 켜둬야 하는 창

검증 중에는 최소 3개 창이 살아 있어야 한다.

1. `VM SSH`
- `uv run uvicorn worker_api:app --host 127.0.0.1 --port 8005`

2. `맥 터미널`
- `ssh -N -L <LOCAL_TUNNEL_PORT>:127.0.0.1:8005 ...`

3. `맥 터미널`
- `uv run uvicorn mobile_app:app --host 127.0.0.1 --port 8008`

셋 중 하나라도 끄면 전체 흐름이 깨질 수 있다.

## E. 자주 나는 오류와 대응

### E-1. `Permission denied (publickey)`

원인:
- 맥 공개키가 `team1`에 등록되지 않았음

대응:
- `GCP 콘솔 SSH`에서 `~/.ssh/authorized_keys`에 맥 공개키 추가

### E-2. 맥에서 `curl http://127.0.0.1:<LOCAL_TUNNEL_PORT>/health` 실패

원인:
- 터널 명령을 VM 안에서 실행했거나, 터널 창을 닫았음

대응:
- 터널은 반드시 `맥 터미널`에서 실행

### E-3. worker health가 `mock`으로 뜸

원인:
- `team1` `.env`에 `IMAGE_BACKEND_KIND=hf_local`이 없음

대응:
- `team1` `.env` 수정 후 워커 재시작

### E-4. VM worker 로그가 안 뜨고 맥 앱만 실패

원인:
- `글+이미지`에서 텍스트(OpenAI) 단계가 먼저 실패했을 가능성

대응:
- 먼저 `이미지만`으로 검증

### E-5. `services.image_service: 백엔드(remote_worker) 타임아웃`

원인:
- 첫 모델 다운로드/초기화 시간이 길어서 로컬 앱 쪽 타임아웃이 먼저 남

대응:
- `맥 터미널`에서 `IMAGE_WORKER_TIMEOUT`을 늘려 재실행

예:

```bash
export IMAGE_WORKER_TIMEOUT=360
```

### E-6. `HF 다운로드 HTTP 에러: 410 ... deprecated`

원인:
- `team1` VM이 current code가 아닌 오래된 브랜치/설정으로 실행 중일 가능성 큼

대응:
- `team1` repo 브랜치와 로컬이 기대하는 계약을 맞춘다
- current code 기준 `/health`는 `image_backend_kind` 키를 반환해야 한다

## F. 빠른 체크 명령 모음

### `team1` 디스크 상태

실행 위치: `VM SSH`

```bash
df -h
du -xh -d 1 ~ 2>/dev/null | sort -h | tail -n 30
```

### 로컬 8008 포트 점유 확인

실행 위치: `맥 터미널`

```bash
lsof -iTCP:8008 -sTCP:LISTEN
```

### `team1` 워커 프로세스 확인

실행 위치: `VM SSH`

```bash
ps -ef | grep worker_api | grep -v grep
```

## G. 변수 치환 예시

문서의 placeholder는 팀 환경에 맞게 바꿔서 사용한다.

- `<TEAM1_VM_EXTERNAL_IP>`: 현재 `team1` 외부 IP
- `<TEAM1_LINUX_USER>`: `whoami`로 확인한 `team1` Linux 사용자명
- `<SSH_PUBLIC_KEY_PATH>`: 예: `~/.ssh/id_ed25519.pub`, `~/.ssh/id_rsa.pub`
- `<SSH_PRIVATE_KEY_PATH>`: 예: `~/.ssh/id_ed25519`, `~/.ssh/id_rsa`
- `<LOCAL_TUNNEL_PORT>`: 로컬에서 안 쓰는 임의 포트. 예: `18005`, `18015`
- `<LOCAL_REPO_PATH>`: 로컬 저장소 경로. 예: `~/workspace/Gen_for_SmallBusiness`

주의:
- 모든 Mac이 `~/.ssh/id_ed25519`를 쓰는 것은 아니다.
- Apple Silicon/macOS에서 `id_ed25519`가 흔하지만, `id_rsa`나 다른 이름의 키를 쓰는 팀원도 있을 수 있다.
- 가장 안전한 방법은 먼저 `ls ~/.ssh/*.pub` 로 공개키 목록을 보고, 실제 사용하는 키 파일을 지정하는 것이다.
