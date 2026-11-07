#!/bin/sh
# Install only after explicit owner approval, on the approved host, owned root:root mode 0750.
set -eu
umask 077
case "${1:-}" in *[!a-f0-9]*|'') echo 'Exact commit required' >&2; exit 2;; esac
[ "${#1}" = 40 ] || exit 2
[ "$(id -u)" = 0 ] || { echo 'Restricted sudo release command required' >&2; exit 2; }
exec 9>/var/lock/eraseproof-deploy.lock
flock -n 9 || { echo 'Another release is active' >&2; exit 2; }
release=/opt/eraseproof/releases/$1
mkdir -p /opt/eraseproof/releases /var/backups/eraseproof
if [ ! -d "$release/.git" ]; then
    git clone --no-checkout https://github.com/bhuvzzs24-spec/Eraseproof-x "$release"
fi
cd "$release"
git fetch origin main
git merge-base --is-ancestor "$1" origin/main
git checkout --detach "$1"
# Do not enable a public listener without the separate owner-approved host record.
python3 -m venv .ops-venv
.ops-venv/bin/pip install -c requirements.lock .
.ops-venv/bin/python - <<'PY'
import json
from pathlib import Path
record=json.loads(Path('/etc/eraseproof/approval.json').read_text())
assert record.get('publication_authorized') is True and record.get('spending_authorized') is True
assert record.get('owner')=='bhuvzzs24-spec'
PY
set -- docker compose --env-file /etc/eraseproof/hosted.env --project-name eraseproof-hosted -f deploy/compose.hosted.yaml
# Fail closed before starting any public service; host record must match the actual origin.
"$@" --profile publish config --format json > /run/eraseproof-resolved.json
.ops-venv/bin/python - <<'PY'
import json
from scripts.hosted_ops import validate
validate(json.load(open('/run/eraseproof-resolved.json')),publish=True,approval=json.load(open('/etc/eraseproof/approval.json')))
PY
rm /run/eraseproof-resolved.json
"$@" build --pull
"$@" up -d --wait postgres redis rabbitmq opensearch
if [ "$("$@" exec -T postgres psql -U lab -d eraseproof -Atc "SELECT to_regclass('public.schema_migrations') IS NOT NULL")" = t ]; then
    "$@" stop gateway customer order cache search analytics deletion verification publisher cache-consumer search-consumer analytics-consumer deletion-scheduler deletion-consumer verification-scheduler verification-worker
    .ops-venv/bin/python scripts/hosted_ops.py backup --env-file /etc/eraseproof/hosted.env --backup "/var/backups/eraseproof/pre-release-$(date -u +%Y%m%dT%H%M%SZ).dump"
fi
"$@" run --rm --no-deps migrate
"$@" run --rm --no-deps provision-verification
.ops-venv/bin/python scripts/hosted_ops.py publish --env-file /etc/eraseproof/hosted.env --approval /etc/eraseproof/approval.json
# Keep the old release for a reviewed, schema-compatible rollback.
ln -sfn "$release" /opt/eraseproof/current.next
mv -Tf /opt/eraseproof/current.next /opt/eraseproof/current
