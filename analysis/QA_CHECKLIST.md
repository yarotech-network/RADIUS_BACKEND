# QA checklist — phase 10 (responsive & accessibility audit)

Verification method used for this pass, per item:

- **Code audit** — breakpoint classes, landmark/heading structure, ARIA roles and
  labels, focus handling, touch-target sizes, `prefers-reduced-motion` handling,
  read from the component source.
- **Unit/component tests** — `src/app/__tests__/shellResponsive.test.tsx` (shells,
  mobile bottom bar, "More" drawer, skip link, `main` landmark, collapsed rail,
  agent tabs), feature tests in `src/features/**` (all screens render their
  mobile card layout and act on it via Testing Library), 180 tests green.
- **Computed** — contrast ratios calculated from the design tokens
  (`src/styles/index.css`) with the WCAG relative-luminance formula.
- **Build gate** — `tsc -b`, `eslint`, `prettier --check`, `vitest`, `vite build`.

Widths follow the phase plan: **375 / 768 / 1280 / 1536 px**. The shell adapts at
`md` (768 — sidebar rail appears, bottom nav hides), `lg` (1024 — full sidebar,
content max-width), `sm` (640 — inline form layouts go two-column), plus the
`xs` (416) custom breakpoint for the tightest phones. Data tables drop
non-essential columns below their `hideBelow` breakpoint and render stacked
mobile cards (`DataTable` `hideBelow`/`mobileHidden`).

Legend: ✅ verified · ⚠️ accepted finding (documented below)

## 1. Global checks (apply to every screen)

| Check | Status | Evidence |
| --- | --- | --- |
| Landmarks on every layout (`header`, `nav`, `main#main`, `aside`) | ✅ | `AppShell`, `AgentLayout`, `PublicLayout`, `PlatformLayout`; tested in `shellResponsive.test.tsx` |
| One `h1` per page | ✅ | Every page renders `PageHeader` (single `h1`); auth/storefront pages use `AuthCard`/hero headings |
| Skip-to-content link, visible on focus | ✅ | Both shells + public layout; asserted in `shellResponsive.test.tsx` |
| `lang="en"`, viewport with `viewport-fit=cover`, theme-color | ✅ | `index.html` |
| Every route sets a document title | ✅ (phase 10) | `src/app/documentTitle.ts` + `RootLayout` (workspace routes); auth/storefront/agent/platform pages set their own; `NotFoundPage` sets a 404 title |
| Focus visible on all interactive elements | ✅ | Global `:focus-visible` outline (`index.css`) + per-component rings; sidebar uses white outline on dark |
| Reduced motion | ✅ | Global `@media (prefers-reduced-motion: reduce)` kills animations/transitions/smooth scroll (`index.css`) |
| Color contrast (text tokens on their backgrounds) | ✅ / ⚠️ | Computed: ink-900 17.9:1, ink-700 10.4:1, ink-600 7.6:1, ink-500 4.8:1 (surface) / 4.6:1 (muted), white on brand-600 5.2:1, badge pairs 4.5–5.5:1, sidebar text 9–16:1 — all ≥ AA. ⚠️ ink-400 (2.6:1) is used only for placeholder hints and disabled controls; every input also has a visible `FormField` label, and disabled controls are exempt — accepted, tracked below |
| Status conveyed by text, not color alone | ✅ | `StatusBadge`/`BooleanBadge` always render a label; dots are decorative (`aria-hidden`) |
| Toasts announced | ✅ | `aria-live="polite"` region; errors use `role="alert"` |
| Loading states announced | ✅ | `Spinner` is `role="status"` + sr-only label; skeletons are `aria-hidden` |
| Forms: label, hint and error wiring | ✅ | `FormField` (label + `aria-describedby` + `role="alert"` error, `aria-invalid`); tested in `FormField.test.tsx` |
| Image-free UI | ✅ | No `<img>`/background images; inline SVG icons are `aria-hidden` with adjacent text or `aria-label`s |

## 2. Keyboard-only run-through

| Component / pattern | Status | Evidence |
| --- | --- | --- |
| Native `<dialog>` modals & drawers (`Dialog`) | ✅ | Browser focus trap, ESC (`cancel`), backdrop click, scroll lock; `aria-labelledby`/`aria-describedby`; close button labelled |
| Dropdown menus (`Menu`) | ✅ (phase 10) | Roving ↑/↓ over `role="menuitem"`, ESC restores focus to the trigger, Tab closes without trapping, selection returns focus to the trigger, outside click closes |
| Tabs (`Tabs`) | ✅ (phase 10) | WAI-ARIA tabs pattern: ←/→/Home/End move focus and activate; selected tab is the only tab stop |
| Segmented filters (`SegmentedControl`) | ✅ (phase 10) | Radiogroup pattern: ←/→/↑/↓ move focus and select; checked option is the only tab stop |
| Mobile "More" navigation drawer | ✅ (phase 10) | Opens with focus moved to the close button; ESC/backdrop/close return focus to the "More" trigger; navigation closes it without focus steal; `role="dialog"` + `aria-modal` |
| Tables → mobile cards | ✅ | Actions stay real buttons/links in the card layout; per-row action menus have per-row `aria-label`s (`Actions for X`) |
| Pagination, filters, search | ✅ | Real buttons/selects/inputs; search announces result count politely (Sessions page) |
| Copy buttons | ✅ | `aria-label` swaps `Copy`/`Copied` |
| Icon-only buttons | ✅ | All 4 instances audited (`AppShell` drawer close, `Dialog` close, plans row menu, vouchers row menu) — all carry `aria-label` |
| Tooltips | ✅ | CSS-only, appear on focus-within as well as hover; exposed via `aria-describedby` |
| Agent wallet / storefront return polling | ✅ | `aria-live="polite"` status regions announce state changes |

## 3. Touch targets (coarse pointers)

| Control | Size | Status |
| --- | --- | --- |
| Mobile bottom nav items (both shells) | 56 px tall | ✅ |
| Standard buttons | 40 px (`md`) / 44 px (`lg`) | ✅ |
| Icon buttons in tables/toolbars | 36 px | ✅ ≥ WCAG 2.2 AA 2.5.8 (24 px min); primary mobile navigation is ≥ 44 px |
| Menu items, nav links | ≥ 40 px row height | ✅ |

## 4. Screen-by-screen checklist

All screens below were audited at the four widths via their responsive
structure (layout breakpoints + `hideBelow`/`mobileHidden` columns + tested
mobile card layouts), and pass the global checks above. "Tests" = the feature's
component test file renders and exercises the screen.

### Public & auth (`PublicLayout`)

| Screen | 375/768/1280/1536 | Keyboard & SR | Tests |
| --- | --- | --- | --- |
| `/login`, `/agent/login` | ✅ centred card, focus order label→input→submit, error `role="alert"` | ✅ | `authFlow.test.tsx` |
| `/register`, `/forgot-password`, `/reset-password` | ✅ single-column form, button full-width on mobile | ✅ | `authFlow.test.tsx` |
| `/accept-invitation` | ✅ as above, token error states | ✅ | `authFlow.test.tsx` |
| `/select-tenant`, `/no-access` | ✅ tenant cards stack; list is keyboard-navigable | ✅ | `authFlow.test.tsx` |
| `/s/:slug` storefront + checkout | ✅ mobile-first single column; plan cards stack; sticky purchase summary | ✅ | `storefront.test.tsx` |
| `/pay/result` | ✅ polling states announced (`aria-live`) | ✅ | `storefront.test.tsx` |
| `/pricing` | ✅ pricing grid collapses to stacked cards | ✅ | `storefront.test.tsx` |
| 404 (`NotFoundPage`) | ✅ centred empty-state | ✅ | — |

### Workspace (`AppShell` — sidebar < 768 px becomes bottom nav + "More" drawer; content max-width 1440)

| Screen | 375/768/1280/1536 | Keyboard & SR | Tests |
| --- | --- | --- | --- |
| `/` Dashboard | ✅ stat grid 1→2→4 cols; attention list stacks | ✅ | `dashboard.test.tsx` |
| `/sessions` Live sessions | ✅ table drops Router/traffic columns on mobile to cards | ✅ | `dashboard.test.tsx` |
| `/plans` Plans | ✅ table→cards; create/edit dialog responsive | ✅ | `PlansPage.test.tsx` |
| `/vouchers` Vouchers | ✅ table→cards, selection + bulk print toolbar wraps | ✅ | `vouchers.test.tsx` |
| `/vouchers/generate` | ✅ two-column form collapses to one | ✅ | `vouchers.test.tsx` |
| `/vouchers/:id` detail | ✅ description list stacks; print sheet hidden on screen | ✅ | `vouchers.test.tsx` |
| `/payments` Payments (+ `?payment=` drawer) | ✅ master/detail collapses to detail-as-page on mobile | ✅ | `payments.test.tsx` |
| `/payments/recovery` Recovery board | ✅ columns → stacked cards | ✅ | `payments.test.tsx` |
| `/routers`, `/routers/new`, `/routers/operations`, `/routers/:id` | ✅ stepped form single column; detail tabs scroll horizontally; tests/secrets panels stack | ✅ | `routers.test.tsx` |
| `/agents`, `/agents/:id` | ✅ table→cards; sales history stacks | ✅ | `agents.test.tsx` |
| `/devices` | ✅ table→cards | ✅ | `devices.test.tsx` |
| `/audit` | ✅ table→expandable cards; filter bar wraps | ✅ | `audit.test.tsx` |
| `/settings/*` (general, billing, team, subscription) | ✅ settings nav becomes tabs; sections stack; secrets write-only fields | ✅ | `settings.test.tsx` |

### Agent portal (`AgentLayout` — top pills ≥ 640 px, bottom tabs below)

| Screen | Widths | Keyboard & SR | Tests |
| --- | --- | --- | --- |
| `/agent` home | ✅ mobile-first; stats + recent sales stack | ✅ | `agent.test.tsx` |
| `/agent/sell` | ✅ single-column flow; result announced `aria-live` | ✅ | `agent.test.tsx` |
| `/agent/wallet` (+ Paystack return) | ✅ fund sheet is a bottom-sheet dialog on mobile; return polling announced | ✅ | `agent.test.tsx` |
| `/agent/vouchers` | ✅ table→cards | ✅ | `agent.test.tsx` |
| `/agent/profile` | ✅ single-column form | ✅ | `agent.test.tsx` |

### Platform console (`AppShell` accent)

| Screen | Widths | Keyboard & SR | Tests |
| --- | --- | --- | --- |
| `/platform` overview | ✅ KPI grid 1→2→4 | ✅ | `platform.test.tsx` |
| `/platform/tenants`, `/platform/tenants/:id` | ✅ table→cards; memberships tab stack | ✅ | `platform.test.tsx` |
| `/platform/routers` | ✅ table→cards | ✅ | `platform.test.tsx` |
| `/platform/payments` (3 sources) | ✅ source tabs scroll; tables→cards | ✅ | `platform.test.tsx` |
| `/platform/staff` | ✅ invitations + grants editors stack | ✅ | `platform.test.tsx` |
| `/platform/audit` | ✅ table→cards | ✅ | `platform.test.tsx` |

## 5. Accepted findings / follow-ups

1. **Placeholder & disabled text contrast (ink-400, 2.6:1)** — placeholders are
   supplementary (every field has a visible label) and disabled controls are
   WCAG-exempt; accepted for this release. If desired, bump placeholders to
   ink-500 (4.8:1) in one place (`Input`/`Textarea`/`Select` classes).
2. **Mobile nav drawer is not a focus trap** — ESC closes it and focus returns to
   the trigger; tabbing past the drawer edge is possible (the drawer is
   `aria-modal` but non-`<dialog>`). All modal dialogs use native `<dialog>`
   with a real trap; the nav drawer is the only exception and is low-risk.
3. **Date/time inputs on iOS** — native pickers are used; visual audit at 375 px
   relies on browser zoom behavior rather than a custom calendar.
