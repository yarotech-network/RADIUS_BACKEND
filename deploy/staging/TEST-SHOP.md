# Requested test frontend and backend domains

Frontend: https://test.yarotech.com.ng (`yarotech-radius-frontend`).
Backend API: https://shop.yarotech.com.ng/api/v1/ (`yarotech-radius-backend`).
Database: a separate `yarotech_radius_staging` target, populated only through reviewed mapping from a restored legacy copy. The original application, live database and live RADIUS service stay untouched. This is a test deployment, not a replacement or production cutover.

Use `backend.test-shop.env.example` for this topology. It allows the shop API host, allows the test frontend origin, and returns browser payment/password-reset flows to the frontend. Secrets remain placeholders and provider/consumer gates remain disabled.

The earlier `stage-radius.yarotech.com.ng` example and combined SPA/API Nginx template do not describe this deployment. Do not install their Nginx/TLS instructions for these domains. Previously built archives still contain the earlier example; select this configuration explicitly when preparing a new package.

## Confirmed VPS routing and prepared additions

The supplied Nginx configuration serves ecommerce from `/var/www/yarotech_ecommerce/dist/client` on shop and the RADIUS React frontend from `/var/www/test.yarotech.com.ng/yarotech-radius-frontend/dist` on test. Both have HTTPS certificates. Gunicorn already occupies 8000 and 8001; 8020 was absent from the supplied listener output. Recheck it immediately before starting a service.

Preserve both existing SPA configurations. `test-shop-api.locations.conf` is a candidate include for their existing HTTPS server blocks: only `/api/v1/` goes to the new isolated backend on 127.0.0.1:8020, while private RADIUS endpoints remain externally blocked. Shop's homepage/assets continue serving ecommerce. Test's `/api/v1/` uses the same backend, so the frontend build configured with `/api/v1` does not need a cross-origin rebuild. The proxy fixes the backend Host header to shop; its existing ALLOWED_HOSTS setting therefore covers either entrypoint.

The supplied configs have no API proxy locations. Reinspect before activation to catch intervening changes or additional includes. Prepare a timestamped backup of each resolved config, add the candidate include only after backend health checks pass, run `nginx -t`, and reload only when validation succeeds. No Nginx change has been executed here. Existing certificate and port80 redirect blocks need no replacement.

The latest locally verified backend revision is `cb4e361` on `email-verification-landing`. The VPS pull fetched that remote revision, but its `Already up to date` message alone does not establish which branch/commit is checked out. Verify the VPS branch, working-tree state and staging files before installing. Do not reset or force-switch a working tree with local changes.

Read-only VPS inspection:

```bash
cat /etc/nginx/sites-enabled/shop.yarotech.com.ng
cat /etc/nginx/sites-enabled/test.yarotech.com.ng
ss -ltnp | grep -E ':(8000|8001|8002|8020|8080|5432|5433|6379)\b'
```

Redact any credentials or private authorization headers before sharing configuration output.
