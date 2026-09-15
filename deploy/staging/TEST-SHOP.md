# Requested test frontend and backend domains

Frontend: https://test.yarotech.com.ng (`yarotech-radius-frontend`).
Backend API: https://shop.yarotech.com.ng/api/v1/ (`yarotech-radius-backend`).
Database: a separate `yarotech_radius_staging` target, populated only through reviewed mapping from a restored legacy copy. The original application, live database and live RADIUS service stay untouched. This is a test deployment, not a replacement or production cutover.

Use `backend.test-shop.env.example` for this topology. It allows the shop API host, allows the test frontend origin, and returns browser payment/password-reset flows to the frontend. Secrets remain placeholders and provider/consumer gates remain disabled.

The earlier `stage-radius.yarotech.com.ng` example and combined SPA/API Nginx template do not describe this deployment. Do not install their Nginx/TLS instructions for these domains. Previously built archives still contain the earlier example; select this configuration explicitly when preparing a new package.

Before changing Nginx, inspect the existing shop and test site configurations and current listeners. Earlier server output showed shop already enabled, so its availability is not established. Do not overwrite its server block or certificates. Prepare the exact Nginx change after confirming which application it serves and whether its API locations are in use.

For direct cross-origin frontend requests, build with `VITE_API_BASE_URL=https://shop.yarotech.com.ng/api/v1`. The existing `/api/v1` build instead needs an explicit API proxy in the test frontend's Nginx site; it does not start calling shop automatically. Choose the wiring after reading the deployed site configurations. No frontend rebuild or VPS change has been performed for this domain clarification.

Read-only VPS inspection:

```bash
cat /etc/nginx/sites-enabled/shop.yarotech.com.ng
cat /etc/nginx/sites-enabled/test.yarotech.com.ng
ss -ltnp | grep -E ':(8000|8001|8002|8020|8080|5432|5433|6379)\b'
```

Redact any credentials or private authorization headers before sharing configuration output.
