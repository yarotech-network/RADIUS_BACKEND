#!/usr/bin/env bash
set -euo pipefail
umask 077
set -a
source /etc/yarotech-radius-staging/backend.env
set +a
[[ "$DB_NAME" == *_staging ]] || { echo 'Wrong database'; exit 1; }
backup_dir=/var/lib/yarotech-radius-staging/backups
mkdir -p "$backup_dir"
backup_file="$backup_dir/$(date -u +%Y%m%dT%H%M%SZ).dump"
[[ ! -e "$backup_file" ]] || { echo 'Backup filename already exists'; exit 1; }
export PGPASSWORD="$DB_PASSWORD"
pg_dump -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -Fc -f "$backup_file" "$DB_NAME"
unset PGPASSWORD
sha256sum "$backup_file" > "$backup_file.sha256"
cat "$backup_file.sha256"
pg_restore --list "$backup_file" >/dev/null
echo 'Archive readable. A separate restore rehearsal is still required.'
