#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

if [ -f .env ]; then
    set -a
    source .env
    set +a
fi

exec .venv/bin/gunicorn \
    --bind 127.0.0.1:5000 \
    --workers 2 \
    --timeout 120 \
    --access-logfile - \
    --error-logfile - \
    app:app
