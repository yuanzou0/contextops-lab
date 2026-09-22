#!/usr/bin/env bash
set -euo pipefail
exec python -m contextops_lab.cli durable-store-drill \
  --redis-server "${REDIS_SERVER:-redis-server}" \
  --output-dir artifacts/redis-drill \
  --report docs/durable-context-redis-drill-results.md
