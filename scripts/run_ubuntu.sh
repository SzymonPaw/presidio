#!/usr/bin/env bash
set -e

cd "$(dirname "$0")/.."

set -a
source .env
set +a

exec .venv/bin/gunicorn \
    --bind 127.0.0.1:5000 \
    --workers 2 \
    --timeout 120 \
    --access-logfile - \
    --error-logfile - \
    app:app
