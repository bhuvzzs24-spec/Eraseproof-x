#!/bin/sh
set -eu
umask 077
# Regenerate both identities from private configuration on every restart.
printf 'user default on >%s ~* &* +@all\nuser verification on >%s ~customer:* ~deletion:customer:* +scan +get +exists +type +ping\n' "$REDIS_PASSWORD" "$VERIFIER_REDIS_PASSWORD" > /data/users.acl
chown redis:redis /data/users.acl
exec docker-entrypoint.sh redis-server --aclfile /data/users.acl --appendonly yes --maxmemory 128mb --maxmemory-policy noeviction
