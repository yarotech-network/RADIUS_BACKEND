# Existing VPS: Paystack test payments and Resend

The backend is already deployed. Its protected environment is
`/etc/yarotech-radius-staging/backend.env`. The activation script creates a new
release and a `.env` symlink to that same file. Both systemd and management
commands therefore use one configuration; never put keys in `.env.example` or Git.
The new backend's `.env.example` documents the variables, but its generic database,
host and Redis defaults must not replace the VPS's verified staging values.

Back up backend.env privately, edit existing entries (no duplicate keys), and add:

```dotenv
STAGING_PROVIDER_TESTING=True
PAYSTACK_SECRET_KEY=sk_test_YOUR_VALUE
PAYSTACK_PUBLIC_KEY=pk_test_YOUR_VALUE
RESEND_API_KEY=re_YOUR_VALUE
DEFAULT_FROM_EMAIL="Yarotech <otp@YOUR_VERIFIED_DOMAIN>"
REGISTRATION_EMAIL_BACKEND=
```

Preserve Django staging settings, DB port5433/database and role
yarotech_radius_staging, Redis DB9, encryption keys, frontend origins and existing
disabled consumer flags. Resend emails are real deliveries; use your own test
accounts. Do not create users in the planned import target unless intentionally
switching it to synthetic testing: the importer requires an empty business target.

The bundle contains `activate-provider-testing.sh`, `staging_settings.py`,
`backend.env.example` and `check_provider_network.py`. Extract into a private root
directory and run the shell script after configuring keys. It copies the current
backend to a new release, validates settings and the actual DB identity, resolves
only api.paystack.co/api.resend.com to public IPs, adds those addresses to the
existing loopback-only systemd policy and switches/restarts only staging.
No migrations, sends, payments, worker starts or Nginx edits are performed.
An ExecStartPre probe checks TLS with hostname validation inside the service
sandbox. This proves connectivity, not key validity or provider acceptance.

On activation failure it restores the previous release and removes its own
provider drop-in. A root-only rollback.sh in the new release performs the same
rollback later. The environment is preserved on rollback; the prior settings
ignore the provider opt-in and keep email disabled. Keep the printed rollback path.

The IP allowlist is a DNS snapshot (not hostname or TCP-port filtering). Provider
addresses may be shared and may change. Do not erase IPAddressDeny to fix a network
failure. Review/refresh the provider drop-in explicitly. Check systemd journal for
unsupported BPF/IP filtering: TLS success alone does not prove deny enforcement.
Keep router and background consumers disabled; no imported work should run yet.

After activation check health endpoints, journal TLS messages and the registration
flow with an intentional test account, followed by a fresh Paystack test purchase.
Plans are currently empty and legacy transfer remains incomplete. Voucher email
delivery uses separate worker commands; no broad scheduler is enabled by this setup.

References: https://paystack.com/docs/api/authentication/ and
https://resend.com/docs/knowledge-base/how-do-i-create-an-email-address-or-sender-in-resend
