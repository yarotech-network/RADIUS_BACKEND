# Ubuntu VPS deployment

These files target one Ubuntu VPS with native PostgreSQL, Redis, Nginx, Gunicorn,
FreeRADIUS, and WireGuard services. Replace `api.example.com` and all example
values before installation. Do not copy the development `.env` to production.

## 1. Prepare DNS and the host

Point the API hostname's A/AAAA records at the VPS and wait for resolution. Create
an operator account with SSH keys, disable password-based root login after verifying
that account, apply Ubuntu security updates, and enable unattended security updates.

Install the application prerequisites:

```bash
sudo apt update
sudo apt install python3 python3-venv python3-dev build-essential libpq-dev \
  postgresql postgresql-client redis-server nginx certbot python3-certbot-nginx \
  libpango-1.0-0 libpangoft2-1.0-0 wireguard-tools openssh-client
sudo adduser --system --group --home /opt/yarotech-radius yarotech
sudo usermod -a -G www-data yarotech
sudo install -d -o yarotech -g www-data -m 0750 /opt/yarotech-radius/backend
sudo install -d -o root -g yarotech -m 0750 /etc/yarotech-radius
```

Allow public SSH, HTTP, and HTTPS only. RADIUS and CoA UDP rules must be limited to
the WireGuard interface or the exact router source networks, never the whole internet.

## 2. Create PostgreSQL and Redis dependencies

Create a least-privilege database role interactively so its password does not enter
shell history:

```bash
sudo -u postgres psql
```

Then use psql's `\password` prompt and create the application database owned by that
role. Keep PostgreSQL and Redis bound to loopback unless another explicitly firewalled
host requires access. Use Redis database 1 for Django cache/replay state.

## 3. Install the reviewed application artifact

Copy or check out the exact reviewed revision under `/opt/yarotech-radius/backend`.
Record its revision and archive checksum, then run:

```bash
cd /opt/yarotech-radius/backend
sudo -u yarotech python3 -m venv venv
sudo -u yarotech ./venv/bin/python -m pip install --upgrade pip
sudo -u yarotech ./venv/bin/python -m pip install -r requirements-production.txt
```

Create `/etc/yarotech-radius/backend.env` from `.env.example`, owned by
`root:yarotech` with mode `0640`. Required production values include:

- `DJANGO_SETTINGS_MODULE=config.production_settings`
- unique `SECRET_KEY` and a newly rotated `FERNET_KEY`
- explicit `ALLOWED_HOSTS`, `CORS_ALLOWED_ORIGINS`, and `CSRF_TRUSTED_ORIGINS`
- local PostgreSQL credentials and `REDIS_URL=redis://127.0.0.1:6379/1`
- `TRUST_X_FORWARDED_PROTO=True` only with the supplied Nginx proxy
- Paystack, SMTP, WireGuard, provisioning-agent, and RADIUS values as applicable

Never reuse the Fernet key that was exposed during development.

## 4. Validate and migrate before starting traffic

Load the environment without printing it, take a verified database backup, and run
the release gates as the service account:

```bash
sudo -u yarotech /bin/bash -c 'set -a; source /etc/yarotech-radius/backend.env; set +a; cd /opt/yarotech-radius/backend; ./venv/bin/python manage.py check --deploy'
sudo -u yarotech /bin/bash -c 'set -a; source /etc/yarotech-radius/backend.env; set +a; cd /opt/yarotech-radius/backend; ./venv/bin/python manage.py migrate --plan'
sudo -u yarotech /bin/bash -c 'set -a; source /etc/yarotech-radius/backend.env; set +a; cd /opt/yarotech-radius/backend; ./venv/bin/python manage.py migrate --noinput'
sudo -u yarotech /bin/bash -c 'set -a; source /etc/yarotech-radius/backend.env; set +a; cd /opt/yarotech-radius/backend; ./venv/bin/python manage.py collectstatic --noinput'
```

Migration execution changes production data and must only occur after the target,
backup, plan, and rollback/forward-recovery decision are confirmed.

## 5. Install Gunicorn and maintenance services

```bash
sudo cp deploy/ubuntu/yarotech-radius.service /etc/systemd/system/
sudo cp deploy/ubuntu/yarotech-radius-maintenance.service /etc/systemd/system/
sudo cp deploy/ubuntu/yarotech-radius-maintenance.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now yarotech-radius.service
sudo systemctl enable --now yarotech-radius-maintenance.timer
sudo systemctl status yarotech-radius.service --no-pager
curl --fail http://127.0.0.1:8000/health/live/
curl --fail http://127.0.0.1:8000/health/ready/
```

## 6. Bootstrap Nginx and TLS

First install the HTTP-only template after replacing the hostname:

```bash
sudo cp deploy/ubuntu/nginx-http-bootstrap.conf.template /etc/nginx/sites-available/yarotech-radius
sudo ln -s /etc/nginx/sites-available/yarotech-radius /etc/nginx/sites-enabled/yarotech-radius
sudo nginx -t
sudo systemctl reload nginx
sudo certbot --nginx -d api.example.com
```

After Certbot has issued the certificate, install the reviewed HTTPS template with
the same real hostname, run `sudo nginx -t`, and reload Nginx. Confirm HTTP redirects,
TLS, `/health/live/`, `/health/ready/`, API authentication, and static admin assets.

## 7. Observe and recover

Use `journalctl -u yarotech-radius.service` and Nginx/PostgreSQL/Redis logs during a
defined observation window. Configure off-host alerts for availability, 5xx rate,
latency, process restarts, disk, database connections, Redis failures, payment
verification failures, and voucher fulfillment failures.

Keep the previous application artifact available. Application rollback is allowed
only while its code remains compatible with the migrated schema. Restore drills,
Fernet rotation, FreeRADIUS's standard PostgreSQL accounting schema, real provider
tests, and a live router/VPS smoke test remain explicit release gates.
