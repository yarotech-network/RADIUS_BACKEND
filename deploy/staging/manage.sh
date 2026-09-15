#!/usr/bin/env bash
set -euo pipefail
set -a
source /etc/yarotech-radius-staging/backend.env
set +a
[[ "$DJANGO_SETTINGS_MODULE" == "config.staging_settings" ]] || { echo 'Wrong settings module'; exit 1; }
[[ "$DB_NAME" == *_staging ]] || { echo 'Wrong database'; exit 1; }
cd /opt/yarotech-radius-staging/current/backend
exec /opt/yarotech-radius-staging/venv/bin/python manage.py "$@"
