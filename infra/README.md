# Infra Guide

이 디렉터리는 `brewgram.duckdns.org` 단일 VM 배포를 위한 템플릿을 담는다.

운영 구조:

```text
Internet
  -> Caddy (80/443, TLS 종료)
  -> mobile_app.py (127.0.0.1:8011)
  -> [optional] worker_api.py (127.0.0.1:8010, remote_worker 모드)
```

핵심 원칙:
- 외부 공개는 `mobile_app`만 한다.
- 기본 `openai_image` 모드에서는 `mobile_app`가 OpenAI 이미지 API를 직접 호출하며 `worker_api`가 필요 없다.
- `remote_worker` 모드에서만 `worker_api`를 같은 VM 내부 루프백(`127.0.0.1`)으로 연다.
- 앱 데이터는 repo 밖 `APP_DATA_DIR`로 분리해 code pull/redeploy와 독립시킨다.
- DuckDNS는 현재 VM IP를 갱신하고, Caddy가 `brewgram.duckdns.org`에 HTTPS를 붙인다.

## 1. 권장 포트

- `Caddy`: `:80`, `:443`
- `mobile_app`: `127.0.0.1:8011`
- `worker_api`: `127.0.0.1:8010` (`remote_worker` 모드에서만)

## 2. 준비물

- DuckDNS 도메인: `brewgram.duckdns.org`
- DuckDNS token
- VM에 clone 된 저장소 경로
- Python/uv 설치
- 운영용 `.env`

## 3. 배포 순서

1. 저장소를 VM에 clone/pull
2. `infra/env/mobile_app.vm.env.example`,
   `infra/env/worker_api.vm.env.example`,
   `infra/env/duckdns.env.example` 를 참고해 운영용 env 작성
3. `infra/scripts/update_duckdns.sh` 에 필요한 DuckDNS env 파일 작성
4. systemd 유닛 설치
5. Caddy 설치 후 `infra/caddy/Caddyfile` 적용
6. `brewgram.duckdns.org` 로 HTTPS 접속 확인

## 4. 권장 파일 배치

예시:

```text
/home/spai0608/Gen_for_SmallBusiness
/srv/brewgram/data
/etc/brewgram/mobile_app.env
/etc/brewgram/worker_api.env
/etc/brewgram/duckdns.env
/etc/caddy/Caddyfile
```

`/etc/brewgram/mobile_app.env` 예시:
- `APP_DATA_DIR=/srv/brewgram/data`
- `OPENAI_API_KEY`
- `IMAGE_BACKEND_KIND=openai_image`
- `FREEIMAGE_API_KEY=...`
- `META_APP_ID=...`
- `META_APP_SECRET=...`
- `TOKEN_ENCRYPTION_KEY=...`
- `META_REDIRECT_URI_MOBILE=https://brewgram.duckdns.org/api/mobile/instagram/callback`
- `ALLOW_DEFAULT_INSTAGRAM_UPLOAD=false` (선택: VM 고정 계정 업로드 시 `true`)
- `META_ACCESS_TOKEN=...` (선택: VM 고정 계정 업로드 시)
- `INSTAGRAM_ACCOUNT_ID=...` (선택: VM 고정 계정 업로드 시)
- `INSTAGRAM_CAPTURE_WORKER_URL=...` (선택, Mac 캡처 워커 사용 시)
- `INSTAGRAM_CAPTURE_WORKER_TOKEN=...` (선택)

`remote_worker` 모드에서만 추가:
- `IMAGE_BACKEND_KIND=remote_worker`
- `IMAGE_WORKER_URL=http://127.0.0.1:8010`
- `IMAGE_WORKER_TOKEN=...`

`/etc/brewgram/worker_api.env` 예시:
- `APP_DATA_DIR=/srv/brewgram/data`
- `OPENAI_API_KEY`
- `IMAGE_BACKEND_KIND=hf_local`
- `IMAGE_WORKER_HOST=127.0.0.1`
- `IMAGE_WORKER_PORT=8010`
- `IMAGE_WORKER_TOKEN=...`

## 5. repo 밖 데이터 디렉토리 준비

운영 데이터는 repo 내부 `data/` 대신 `/srv/brewgram/data`를 사용한다.
이렇게 하면 git pull / 재배포와 무관하게 DB, 생성 이미지, 온보딩 파일이 유지된다.

초기 1회:

```bash
sudo install -d -o spai0608 -g spai0608 /srv/brewgram/data
rsync -a /home/spai0608/Gen_for_SmallBusiness/data/ /srv/brewgram/data/
```

그 다음 `/etc/brewgram/mobile_app.env`, `/etc/brewgram/worker_api.env`에
`APP_DATA_DIR=/srv/brewgram/data`를 넣는다.
## 6. 설치 명령 예시

systemd 유닛 복사:

```bash
sudo cp infra/systemd/brewgram-mobile.service /etc/systemd/system/
sudo cp infra/systemd/brewgram-worker.service /etc/systemd/system/
sudo cp infra/systemd/duckdns-refresh.service /etc/systemd/system/
sudo cp infra/systemd/duckdns-refresh.timer /etc/systemd/system/
```

DuckDNS 스크립트 설치:

```bash
sudo install -m 755 infra/scripts/update_duckdns.sh /usr/local/bin/update_duckdns.sh
sudo install -m 755 infra/scripts/deploy_brewgram.sh /usr/local/bin/deploy-brewgram.sh
```

Caddy 설정:

```bash
sudo cp infra/caddy/Caddyfile /etc/caddy/Caddyfile
sudo systemctl reload caddy
```

서비스 활성화:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now brewgram-mobile.service
sudo systemctl enable --now duckdns-refresh.timer
```

`remote_worker` 모드일 때만:

```bash
sudo systemctl enable --now brewgram-worker.service
```

## 7. 점검 명령

로컬 VM:

```bash
curl http://127.0.0.1:8011/health
curl -I http://127.0.0.1:8011/stitch/manifest.webmanifest
```

`remote_worker` 모드일 때만:

```bash
curl http://127.0.0.1:8010/health
```

외부:

```bash
curl -I https://brewgram.duckdns.org/
curl -I https://brewgram.duckdns.org/stitch/manifest.webmanifest
curl -I https://brewgram.duckdns.org/stitch/service-worker.js
```

## 8. Meta OAuth E2E 전 마지막 체크

- `brewgram.duckdns.org` HTTPS 정상
- `META_REDIRECT_URI_MOBILE` 운영 도메인으로 설정
- Meta 앱의 Valid OAuth Redirect URIs 에
  `https://brewgram.duckdns.org/api/mobile/instagram/callback` 추가
- 테스트 계정 App Role / Facebook Page 권한 확인
- 모바일 업로드는 기본적으로 OAuth로 직접 연결된 계정만 사용. 내부 데모에서 VM 고정 계정을 쓰려면 `ALLOW_DEFAULT_INSTAGRAM_UPLOAD=true`, `META_ACCESS_TOKEN`, `INSTAGRAM_ACCOUNT_ID`를 함께 설정

## 9. 배포 운영 기준

현재 repo에서는 GitHub Actions 자동 배포를 사용하지 않는다.
VM 반영은 SSH로 접속한 뒤 수동 배포 스크립트 또는 수동 명령을 실행한다.

수동 배포 스크립트:

```bash
BREWGRAM_DEPLOY_BRANCH=codex/oauth-only-mobile-upload deploy-brewgram.sh
```

브랜치를 바꿀 때는 `BREWGRAM_DEPLOY_BRANCH` 값만 바꾼다.

수동 명령:

```bash
cd ~/Gen_for_SmallBusiness
git fetch origin
git switch codex/oauth-only-mobile-upload
git pull --ff-only origin codex/oauth-only-mobile-upload
uv sync
uv run python -m playwright install chromium
sudo systemctl restart brewgram-mobile.service
```

`remote_worker` 모드이면 마지막 줄 대신:

```bash
sudo systemctl restart brewgram-worker.service brewgram-mobile.service
```

주의:
- Playwright Chromium 실행에 필요한 OS 패키지는 VM 최초 세팅 때 `sudo env PATH="$PATH" /home/spai0608/.local/bin/uv run python -m playwright install-deps chromium`으로 1회 설치한다.
- VM 작업 트리에 수동 수정이 남아 있으면 `git pull --ff-only`가 실패할 수 있다.
