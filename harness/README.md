# Backend verification harness (SQLite)

Runs the **unmodified** Django backend on SQLite so the frontend can be exercised against the real
API where PostgreSQL is unavailable. Verification only — production stays PostgreSQL + FreeRADIUS.

```bash
# from the backend checkout root (the directory containing manage.py)
python3 -m venv .venv-harness && . .venv-harness/bin/activate
pip install django==5.2.17 djangorestframework==3.15.2 djangorestframework-simplejwt==5.3.1 \
  python-decouple==3.8 django-cors-headers==4.4.0 django-filter==24.3 drf-spectacular==0.27.2 \
  requests==2.32.3 qrcode==7.4.2 Pillow==10.4.0 cryptography==43.0.0 pyotp==2.9.0 fpdf2==2.7.9

export PYTHONPATH=$PWD/frontend/harness:$PWD DJANGO_SETTINGS_MODULE=harness_settings
python manage.py migrate --noinput
sqlite3 frontend/harness/harness.sqlite3 < frontend/harness/create_radius_tables.sql   # or run the SQL via python
python frontend/harness/seed.py            # users: admin owner manager staff pstaff pstaff1 agent agent2 nobody — password Passw0rd!2026
python manage.py runserver 127.0.0.1:8000
```

Then in `frontend/`: `npm run dev` (proxies `/api` to :8000) and `npm run test:integration`.

Notes

- `weasyprint` is not installed → `vouchers/pdf/` answers 503, which is exactly the fallback path the UI must handle.
- Paystack / WireGuard / SSH / SMTP are not configured → the related commands return their documented 503/409 responses.
- Throttles are left on so 429 handling can be checked (`LIVE_API_THROTTLE=1 npm run test:integration`).
