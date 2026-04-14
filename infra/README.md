# Infra Guide

이 디렉터리는 `brewgram.duckdns.org` 단일 VM 배포를 위한 템플릿을 담는다.

운영 구조:

```text
Internet
  -> Caddy (80/443, TLS 종료)
  -> mobile_app.py (127.0.0.1:8007)
  -> worker_api.py (127.0.0.1:8006)
```

핵심 원칙:
- 외부 공개는 `mobile_app`만 한다.
- `worker_api`는 같은 VM 내부 루프백(`127.0.0.1`)으로만 연다.
- `mobile_app`는 `IMAGE_BACKEND_KIND=remote_worker`,
  `IMAGE_WORKER_URL=http://127.0.0.1:8006`으로 내부 워커를 호출한다.
- DuckDNS는 현재 VM IP를 갱신하고, Caddy가 `brewgram.duckdns.org`에 HTTPS를 붙인다.

## 1. 권장 포트

- `Caddy`: `:80`, `:443`
- `mobile_app`: `127.0.0.1:8007`
- `worker_api`: `127.0.0.1:8006`

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
/opt/brewgram/Gen_for_SmallBusiness
/etc/brewgram/mobile_app.env
/etc/brewgram/worker_api.env
/etc/brewgram/duckdns.env
/etc/caddy/Caddyfile
```

`/etc/brewgram/mobile_app.env` 예시:
- `OPENAI_API_KEY`
- `IMAGE_BACKEND_KIND=remote_worker`
- `IMAGE_WORKER_URL=http://127.0.0.1:8006`
- `IMAGE_WORKER_TOKEN=...`
- `FREEIMAGE_API_KEY=...`
- `META_APP_ID=...`
- `META_APP_SECRET=...`
- `TOKEN_ENCRYPTION_KEY=...`
- `META_REDIRECT_URI_MOBILE=https://brewgram.duckdns.org/api/mobile/instagram/callback`

`/etc/brewgram/worker_api.env` 예시:
- `OPENAI_API_KEY`
- `IMAGE_BACKEND_KIND=hf_local`
- `IMAGE_WORKER_HOST=127.0.0.1`
- `IMAGE_WORKER_PORT=8006`
- `IMAGE_WORKER_TOKEN=...`

## 5. 설치 명령 예시

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
```

Caddy 설정:

```bash
sudo cp infra/caddy/Caddyfile /etc/caddy/Caddyfile
sudo systemctl reload caddy
```

서비스 활성화:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now brewgram-worker.service
sudo systemctl enable --now brewgram-mobile.service
sudo systemctl enable --now duckdns-refresh.timer
```

## 6. 점검 명령

로컬 VM:

```bash
curl http://127.0.0.1:8006/health
curl http://127.0.0.1:8007/health
curl -I http://127.0.0.1:8007/stitch/manifest.webmanifest
```

외부:

```bash
curl -I https://brewgram.duckdns.org/
curl -I https://brewgram.duckdns.org/stitch/manifest.webmanifest
curl -I https://brewgram.duckdns.org/stitch/service-worker.js
```

## 7. Meta OAuth E2E 전 마지막 체크

- `brewgram.duckdns.org` HTTPS 정상
- `META_REDIRECT_URI_MOBILE` 운영 도메인으로 설정
- Meta 앱의 Valid OAuth Redirect URIs 에
  `https://brewgram.duckdns.org/api/mobile/instagram/callback` 추가
- 테스트 계정 App Role / Facebook Page 권한 확인
