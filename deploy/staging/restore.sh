#!/usr/bin/env bash
set -euo pipefail
umask 077
[[ $# -eq 2 ]] || { echo 'Usage: restore.sh BACKUP.dump NEW_RESTORE_DATABASE'; exit 1; }
set -a
source /etc/yarotech-radius-staging/backend.env
set +a
[[ "$DB_NAME" == *_staging ]] || { echo 'Wrong staging environment'; exit 1; }
restore_db="$2"
[[ "$restore_db" =~ ^yarotech_restore_[a-zA-Z0-9_]+_staging$ && "$restore_db" != "$DB_NAME" ]] || { echo 'Use a separate yarotech_restore_*_staging database'; exit 1; }
backup_file=$(realpath -e -- "$1")
[[ "$backup_file" == /var/lib/yarotech-radius-staging/backups/*.dump ]] || { echo 'Use a backup from the staging backup directory'; exit 1; }
sha256sum -c "$backup_file.sha256"
export PGPASSWORD="$DB_PASSWORD"
table_count=$(psql -X -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$restore_db" -A -t -v ON_ERROR_STOP=1 -c "SELECT count(*) FROM information_schema.tables WHERE table_schema='public'")
[[ "$table_count" == 0 ]] || { echo 'Restore target is not empty; refusing overwrite'; exit 1; }
pg_restore --exit-on-error --single-transaction --no-owner --no-privileges -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$restore_db" "$backup_file"
unset PGPASSWORD
echo 'Restore completed in the separate database. Compare counts, financial totals and key decryption before accepting recovery.'
