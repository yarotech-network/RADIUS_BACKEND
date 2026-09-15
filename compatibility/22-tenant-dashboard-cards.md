# Tenant dashboard cards

## Plan and reference

Reference: `yarotech-radius-system-current/templates/tenant/dashboard.html`,
`templates/dashboard.html`, and their view functions in `vouchers/views.py`.
The new dashboard currently has four business cards and a single accounting-session
preview. It lacks daily/monthly revenue, failed/successful payment counts, usage
breakdowns, subscription context and aggregate network traffic.

Implement grouped cards with drill-down links on the tenant dashboard; reuse the
network panel on live sessions. Keep current paginated payment, voucher, plan and
router pages as the detailed destinations. Preserve platform dashboard boundaries.

Backend: extend stats additively and add a separately authorized network-summary
endpoint. Aggregate tenant-scoped records in SQL. Use NGN kobo throughout; online
payments, wallet voucher charges and credit repayments are separate recorded
sources. Unpaid credit, complimentary vouchers, printing and wallet funding are
not collected revenue. Old manual revenue history needs a separate import mapping;
do not invent it from current plan prices. Retain `total_revenue` as online revenue
for existing consumers and add explicit collected-revenue fields.

Network: use unambiguous tenant NAS addresses and tenant voucher identities for
HotSpot metrics. Fresh open accounting records drive online counts; stale records
are separate. Standard FreeRADIUS `acctupdatetime` is an unmanaged model mapping,
with a state-only migration and no SQL table alteration. Traffic labelled as today's
sessions includes cumulative counters of sessions active today, matching the old
source; it is not a midnight delta. Speed is measured between accounting updates,
never calculated from a page of users. Missing samples are unavailable, not zero.
Router configuration state alone is not proof of connectivity.

Frontend: add API types and tenant-scoped query keys for new metrics, grouped
responsive cards, subscription summary, explicit loading/error/stale states,
role-gated links and polling. No new third-party dependencies. No provider calls,
physical-router operations or money movement occur from dashboard reads.

Validation: focused PostgreSQL tests for tenant isolation, financial source
deduplication, date boundaries, stale accounting and counter resets; frontend tests
for cards/links/unavailable states, then typecheck, lint and production build.
Backend deployment and migration precede the frontend; no live migration or VPS
deployment is part of this change.

## Implemented placement

| Legacy card or section | New location |
| --- | --- |
| Subscription, trial, expiry, days remaining, router allowance | Dashboard subscription summary, linked to Settings / Subscription |
| Today's, monthly and lifetime revenue | Dashboard revenue and payments section, with recorded collection sources |
| Successful, pending, failed payments | Dashboard cards linking to the matching Payments status filter |
| Total and active vouchers | Dashboard overview |
| Available, sold, used, expired, active, not-started vouchers | Dashboard voucher section and overview; disabled count added |
| Voucher sales today | Vouchers issued today, reflecting the legacy query's actual meaning |
| Total and active plans | Dashboard voucher and plan section, linked to Plans |
| Online users, live HotSpot users, active sessions | Fresh accounting session counts; distinct online vouchers shown separately |
| Current upload and download speed | Live HotSpot panel, with the contributing sample count |
| Bandwidth today, upload, download, live and lifetime traffic | Live HotSpot panel, with cumulative-session accounting basis explained |
| Sessions today | Live HotSpot panel |
| Online, offline and total routers | Network health and overview; unknown, inactive and awaiting-import counts kept separate |
| Users per router and router health | Network panel, linked to router details |
| Recent payments, vouchers and plans | Existing paginated module pages via the new section links |
| Recent live session details | Existing dashboard session preview and Live sessions directory |

The network panel is also available on Live sessions; its aggregates cover the
whole workspace and are explicitly independent of directory filters. Pausing that
page stops automatic network-summary polling too. All figures are reporting reads;
no read request expires a voucher, probes a router, sends a message or moves money.

No historical online-user chart is fabricated from current sessions. The legacy
platform chart widgets are outside these tenant metric cards.

## Deployment handoff

Deploy the backend before rebuilding the frontend. The new migration
`vouchers.0010_accounting_update_state` maps the existing FreeRADIUS column
`radacct.acctupdatetime`; it contains no database DDL. Run `check_radius_schema`
against the isolated deployment before activation. Missing accounting tables or
columns return an unavailable network summary rather than false zero counts.

Speeds use the configured Django cache, tenant-separated keys and bounded samples.
Production/staging should use the existing shared Redis cache. A cold cache, reset
counter, new session or cache outage may leave speeds unavailable while counts and
cumulative traffic remain usable. The five-minute freshness window assumes regular
interim updates (the prepared router script uses a shorter interval).

Legacy manual-revenue records are not present in the new models and still require
an explicit import mapping before historical totals can be reconciled. The UI
reports recorded collections only; printed vouchers and old balances are not
converted into invented revenue.

## Validation

- 62 PostgreSQL-backed dashboard, API workflow, device accounting and subscription
  access tests passed, including the new tenant and delegated-staff boundaries.
- 15 frontend dashboard, card and session tests passed.
- The final five card tests passed again after the countdown and fixture checks.
- Final TypeScript and production build passed. Vite retained non-blocking Zod
  annotation and existing subscription-module chunk warnings.
- Scoped frontend lint passed; migration consistency reported no changes needed.
- Full schema generation retains unrelated pre-existing serializer/authenticator
  diagnostics. Only the dashboard path/components were refreshed in OpenAPI; the
  new endpoint explicitly declares JWT authentication and a 503 response.
- VPS activation, real accounting traffic, manual-revenue import reconciliation
  and physical-router verification remain unperformed.
