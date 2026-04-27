#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${BREWGRAM_APP_DIR:-/home/spai0608/Gen_for_SmallBusiness}"
BRANCH="${BREWGRAM_DEPLOY_BRANCH:-main}"
UV_BIN="${BREWGRAM_UV_BIN:-/home/spai0608/.local/bin/uv}"
PLAYWRIGHT_BROWSER="${BREWGRAM_PLAYWRIGHT_BROWSER:-chromium}"

cd "${APP_DIR}"

echo "[deploy] fetching latest branch: ${BRANCH}"
git fetch origin
if git show-ref --verify --quiet "refs/heads/${BRANCH}"; then
  git switch "${BRANCH}"
else
  git switch -t "origin/${BRANCH}"
fi
git pull --ff-only origin "${BRANCH}"

if [[ "${BREWGRAM_SKIP_UV_SYNC:-0}" != "1" ]]; then
  echo "[deploy] syncing dependencies"
  "${UV_BIN}" sync
fi

if [[ "${BREWGRAM_SKIP_PLAYWRIGHT_INSTALL:-0}" != "1" ]]; then
  echo "[deploy] ensuring Playwright browser: ${PLAYWRIGHT_BROWSER}"
  "${UV_BIN}" run python -m playwright install "${PLAYWRIGHT_BROWSER}"
fi

echo "[deploy] restarting services"
sudo systemctl daemon-reload
sudo systemctl restart brewgram-worker.service
sudo systemctl restart brewgram-mobile.service

echo "[deploy] waiting for services"
sleep 5
sudo systemctl is-active brewgram-worker.service >/dev/null
sudo systemctl is-active brewgram-mobile.service >/dev/null

curl -fsS http://127.0.0.1:8011/stitch/manifest.webmanifest >/dev/null
curl -fsS https://brewgram.duckdns.org/stitch/manifest.webmanifest >/dev/null

echo "[deploy] ok"
