#!/usr/bin/env bash
set -euo pipefail

if [[ -z "${DUCKDNS_TOKEN:-}" ]]; then
  echo "DUCKDNS_TOKEN is required" >&2
  exit 1
fi

if [[ -z "${DUCKDNS_DOMAINS:-}" ]]; then
  echo "DUCKDNS_DOMAINS is required" >&2
  exit 1
fi

response="$(curl -fsS "https://www.duckdns.org/update?domains=${DUCKDNS_DOMAINS}&token=${DUCKDNS_TOKEN}&ip=")"

if [[ "${response}" != "OK" ]]; then
  echo "DuckDNS update failed: ${response}" >&2
  exit 1
fi

echo "DuckDNS updated: ${DUCKDNS_DOMAINS}"
