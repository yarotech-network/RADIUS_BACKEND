# Email-first registration

Current: RegisterSerializer creates user, tenant and membership, then RegisterView sends a user-bound code. VerifyEmailView activates and returns login tokens. Tenant.slug already uniquely identifies storefront URLs. Existing endpoints and old verification flows must remain compatible.

New flow: POST /auth/registration/email/ requests a six-digit code without creating an account; POST /auth/registration/email/verify/ exchanges it for a short-lived, single-use registration token; POST /auth/registration/ creates verified owner, named tenant with chosen workspace ID/slug, and membership atomically. No login tokens are returned; the ready screen links to sign in. Phone remains a business contact field in step two, never verified. Username stays because existing login requires it. First and last name are supported. No persona/referral/Telegram fields.

Persistence: additive RegistrationEmailChallenge table keyed by normalized email with UUID, HMAC code/token hashes, expiry, attempts, sent/verified/consumed timestamps. Code TTL 10 minutes, 5 attempts, resend cooldown 60 seconds; proof TTL 30 minutes. Lock per email/challenge for verification and consumption; database uniqueness protects workspace/user claims. Email delivery outside transaction; failures surfaced, retry allowed. Expired records prunable via command. Proof and passwords stay only in browser memory, never URLs/storage/logs. Anonymous endpoints use scoped IP throttles and no-store responses. Old registration endpoints unchanged.

Frontend: isolated RegistrationLayout and three-step RegisterPage with accessible progress, forms, editable slug auto-derived until edited, server errors, resend countdown, step focus, ready links. WhatsApp/guide URLs are configuration; missing WhatsApp stays visibly unavailable. Local guide fallback if no URL supplied. Existing /verify-email remains for legacy signups.

Deployment: apply additive accounts migration before backend endpoints, then frontend. No existing data backfill/drop. Rollback app first; leave harmless new table in place. Test schema state, new API happy path, invalid/expired/exhausted codes, missing/expired/replayed proof, email binding, uniqueness and rollback, provider failures, old verification compatibility; React transitions/errors and browser widths. Live SMTP delivery and production concurrency cannot be inferred from local tests.

## Validation

2026-09-08: New registration plus legacy verification tests: 23 passed. Full apps.accounts suite: 40 passed, one existing optional browser test skipped. Tests ran against PostgreSQL, including simultaneous proof consumption (one workspace only) and injected membership failure (user/tenant/proof changes roll back). Local migration 0005 is applied; makemigrations --check reports no drift. Run prune_registration_challenges daily to remove proofs expired more than a day ago. No live verification email or production signup was initiated by this task.
