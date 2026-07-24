#!/usr/bin/env sh
# Wait for PostgreSQL, apply migrations, then hand over to the CMD.
set -e

: "${POSTGRES_HOST:=postgres}"
: "${POSTGRES_PORT:=5432}"
: "${WAIT_FOR_DB_SECONDS:=60}"
: "${RUN_MIGRATIONS:=true}"

echo "==> waiting for postgres at ${POSTGRES_HOST}:${POSTGRES_PORT}"
elapsed=0
until python - <<'PY' 2>/dev/null
import os, socket, sys
s = socket.socket()
s.settimeout(2)
try:
    s.connect((os.environ.get("POSTGRES_HOST", "postgres"),
               int(os.environ.get("POSTGRES_PORT", 5432))))
except OSError:
    sys.exit(1)
finally:
    s.close()
PY
do
    elapsed=$((elapsed + 2))
    if [ "$elapsed" -ge "$WAIT_FOR_DB_SECONDS" ]; then
        echo "!! postgres unreachable after ${WAIT_FOR_DB_SECONDS}s" >&2
        exit 1
    fi
    sleep 2
done
echo "==> postgres is up"

if [ "$RUN_MIGRATIONS" = "true" ]; then
    echo "==> alembic upgrade head"
    alembic upgrade head
fi

echo "==> starting: $*"
exec "$@"