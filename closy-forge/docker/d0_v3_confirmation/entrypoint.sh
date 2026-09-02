#!/bin/sh
set -eu

route_id="${ROUTE_ID:-}"
exec /usr/bin/env -i \
  LANG=C.UTF-8 \
  LC_ALL=C.UTF-8 \
  PATH=/usr/local/bin:/usr/bin:/bin \
  PYTHONHASHSEED=0 \
  ROUTE_ID="$route_id" \
  python -I /app/runner_v3.py
