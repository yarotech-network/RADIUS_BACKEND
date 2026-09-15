#!/usr/bin/env bash
# Operator-run on the VPS, after editing the protected runtime environment.
set -euo pipefail
umask 022
[[ $(id -u) == 0 ]] || { echo 'Run as root.'; exit 1; }
bundle=$(cd -- "$(dirname -- "$0")" && pwd)
base=/opt/yarotech-radius-staging
service=yarotech-radius-staging.service
envfile=/etc/yarotech-radius-staging/backend.env
old_release=$(readlink -f "$base/current")
[[ "$old_release" == "$base/releases/"* ]] || { echo 'Unexpected current release.'; exit 1; }
test -f "$bundle/staging_settings.py"
test -f "$bundle/backend.env.example"
test -f "$bundle/check_provider_network.py"
test -f "$envfile"
set -a
source "$envfile"
set +a
[[ "$DJANGO_SETTINGS_MODULE" == config.staging_settings && "$DB_NAME" == yarotech_radius_staging && "$DB_USER" == yarotech_radius_staging && "$DB_HOST" == 127.0.0.1 && "$DB_PORT" == 5433 ]] || { echo 'Unexpected staging database settings.'; exit 1; }
[[ "${STAGING_PROVIDER_TESTING:-}" == True ]] || { echo 'Set STAGING_PROVIDER_TESTING=True in backend.env first.'; exit 1; }
release=$(mktemp -d "$base/releases/provider-testing.XXXXXX")
chmod 755 "$release"
cp -a "$old_release/backend" "$release/backend"
install -m 0644 "$bundle/staging_settings.py" "$release/backend/config/staging_settings.py"
install -m 0644 "$bundle/backend.env.example" "$release/backend/.env.example"
install -m 0644 "$bundle/check_provider_network.py" "$release/check_provider_network.py"
# Never replace a separate environment file or copy secrets into the release.
if test -e "$release/backend/.env" || test -L "$release/backend/.env"; then
    echo 'Candidate already contains .env; stop for review.'
    exit 1
fi
ln -s "$envfile" "$release/backend/.env"
cd "$release/backend"
"$base/venv/bin/python" manage.py check --deploy --tag security
"$base/venv/bin/python" manage.py shell -c "
from django.conf import settings
from django.db import connection
assert settings.STAGING_MODE and settings.STAGING_PROVIDER_TESTING
with connection.cursor() as c:
    c.execute('SELECT current_database(), current_user')
    assert c.fetchone() == ('yarotech_radius_staging', 'yarotech_radius_staging')
print('Provider settings and staging database verified; no provider messages sent.')
"
dropdir=/etc/systemd/system/yarotech-radius-staging.service.d
dropfile="$dropdir/30-provider-testing.conf"
test ! -e "$dropfile" || { echo 'Provider drop-in already exists. Stop for review.'; exit 1; }
mkdir -p "$dropdir"
candidate="$release/provider-network.conf"
"$base/venv/bin/python" - "$candidate" <<'PY'
import ipaddress
import socket
import sys
from pathlib import Path

addresses = set()
for host in ('api.paystack.co', 'api.resend.com'):
    resolved = {item[4][0] for item in socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)}
    if not resolved or any(not ipaddress.ip_address(ip).is_global for ip in resolved):
        raise SystemExit('Provider DNS did not return only public addresses; stop for review.')
    addresses.update(resolved)
content = '[Service]\nIPAddressDeny=any\nIPAddressAllow=localhost\n'
content += ''.join('IPAddressAllow=' + ip + '\n' for ip in sorted(addresses))
Path(sys.argv[1]).write_text(content)
print('Resolved provider IP allowlist; refresh explicitly if provider DNS changes.')
PY
printf 'ExecStartPre=%s/venv/bin/python %s/check_provider_network.py\n' "$base" "$release" >> "$candidate"
rollback="$release/rollback.sh"
cat > "$rollback" <<EOF
#!/usr/bin/env bash
set -euo pipefail
ln -sfnT '$old_release' '$base/current'
rm -f -- '$dropfile'
systemctl daemon-reload
systemctl restart '$service'
EOF
chmod 700 "$rollback"
sha256sum config/staging_settings.py > "$release/provider-settings.sha256"
printf '%s\n' "$old_release" > "$release/previous-release.txt"
printf 'Rollback command: bash %s\n' "$rollback"
trap 'echo "Activation failed; restoring previous release."; bash "$rollback"' ERR
install -m 0644 "$candidate" "$dropfile"
systemctl daemon-reload
ln -sfnT "$release" "$base/current"
systemctl restart "$service"
curl --fail --silent --show-error --retry 5 --retry-connrefused --retry-delay 2 --max-time 10 -H 'Host: shop.yarotech.com.ng' http://127.0.0.1:8020/health/ready/
trap - ERR
printf '\nProvider-testing release active: %s\n' "$release"
printf 'Runtime .env: %s/current/backend/.env\n' "$base"
systemctl --no-pager --full status "$service"
