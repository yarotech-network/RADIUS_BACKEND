# PPPoE PAP integration - Phase 6B

This is a new authentication path, separate from existing Hotspot SQL vouchers. No router or FreeRADIUS configuration has been applied by the application. The endpoint and template target FreeRADIUS 3.2, PAP and IPv4 NAS transport. CHAP/MS-CHAP, IPv6 transport, multi-service subscribers and existing-router migration are not enabled in this delivery.

## Deployment

1. Apply customers.0002 (inspect the exact generated migration name), deploy the backend and set a dedicated random PPPOE_RADIUS_TOKEN of at least 32 characters. Use the same value as YAROTECH_PPPOE_TOKEN in the FreeRADIUS service environment. Set YAROTECH_API_ORIGIN to the trusted HTTPS backend origin (loopback HTTP is suitable only when both services share the same host). Do not use a user JWT, router shared secret, or expose tokens in screenshots/logs.
2. Restrict /api/v1/radius/pppoe/decision/ to your FreeRADIUS hosts at the reverse proxy/firewall. Redact request bodies and X-Radius-Token from proxy/APM/debug logs. Keep certificate verification enabled. The token authorizes authentication decisions, not dashboard access.
3. Install/enable rlm_rest and the adjacent module template. Review the snippets below against the existing virtual server. Place the reserved username branch before existing SQL/PAP handlers in authorize. No reserved-name request may fall through to voucher authorization, including on timeout or failure.
4. Add this branch to authorize:

```text
if (&User-Name =~ /^yrp-/) {
    if (!&User-Password || &CHAP-Password || &MS-CHAP-Challenge) {
        reject
    }
    update control {
        Auth-Type := Yarotech-PAP
    }
    return
}
```

Add this block inside authenticate:

```text
Auth-Type Yarotech-PAP {
    update control {
        REST-HTTP-Header := "X-Radius-Token: $ENV{YAROTECH_PPPOE_TOKEN}"
    }
    yarotech_pppoe
    if (ok || updated) {
        ok
    }
    else {
        reject
    }
}
```

The module form encoder uses explicit urlencode expansions. Responses disable value expansion for every returned attribute. The endpoint checks the actual packet source IP, not the NAS-IP-Address claim. Only the uniquely owned assigned router address is accepted. Do not substitute a user-controlled source field.

5. Preserve normal SQL accounting for PPP sessions. Ensure /ppp aaa uses RADIUS and accounting, an enabled RADIUS entry serves PPP, the PPPoE server accepts PAP, and its existing local/remote address pool is correct. Local PPP secrets can bypass RADIUS: resolve any conflicting reserved usernames before lab testing. The app does not alter pools, bridges, WAN, firewall or local secrets.
6. Review and install the updated maintenance service/timer. `python manage.py reconcile_pppoe_services --limit 25` checks the oldest services first. Each service has a five-minute crash-recoverable lease and at most ten disconnect attempts per scan. Run frequently enough for the fleet size; database/accounting/CoA failures remain visible as failed cleanup, and the command exits nonzero. Never interpret an ACK as proof of disconnect; stop-accounting confirms it.

## Behavior

Create a PPPoE plan, open a customer detail panel and assign that plan/router with a device password. The username is generated in the reserved yrp- namespace. Passwords use Django password hashing, are write-only and cannot be recovered. No PPPoE credentials are copied into radcheck or radreply. Existing Hotspot credentials remain unchanged.

The service expiry and speed are snapshots. Changing plan availability does not change issued services. Manual renewal extends from the later of now/current expiry by one original period; it records no payment and preserves suspension. A stale version returns 409; repeat the same idempotency key to recover an uncertain renewal result. Cancel and reopen the action to load a refreshed version after another operator changes the service.

Every PAP request checks password, tenant/customer/router eligibility, exact assigned source, PPP service attributes, suspension and expiry. Session-Timeout is capped at one hour (or the remaining lifetime), so clients must reconnect/re-authenticate at least hourly. This bounds access when CoA is unavailable. Plan prices are informational until payment-to-service integration is implemented.

Suspension/password rotation schedules old-session cleanup without making a synchronous network request. Reconciliation does not alter accounting stop times. Unknown-start-time sessions are treated conservatively as old sessions. Customer archiving requires a suspended service and does not free its identifier.

## Lab acceptance and rollback

Run freeradius -XC against the installed configuration, then test PAP accept and wrong-password reject; wrong router and ambiguous NAS rejection; expired/suspended rejection; failed REST/API responses with no SQL fallback; speed/Session-Timeout; accounting start/interim/stop; CoA ACK, timeout and recovery; renewal replay; and password replacement. Real FreeRADIUS parser/transport, router enforcement and load tests remain unverified locally.

Deploy the additive migration before code. Preserve both new tables and hashed credentials on application rollback. Keep the reserved-prefix reject branch if disabling REST, so subscriber usernames cannot fall through to SQL. Disabling the decision endpoint must reject, not silently enable a different authentication path. Do not drop subscriber records as a rollback procedure.

Primary references: https://github.com/FreeRADIUS/freeradius-server/blob/v3.2.x/raddb/mods-available/rest and https://help.mikrotik.com/docs/spaces/ROS/pages/328097/RADIUS
