# 04 — Design System

A bright, professional ISP-operations look: white surfaces, blue for actions, dark blue used deliberately for navigation and emphasis. No gradients, minimal shadows, information density tuned for operators.

---

## 1. Color tokens (Tailwind v4 `@theme`)

| Token | Value | Use |
|---|---|---|
| `--color-brand-950` | `#0B1F3F` | Sidebar background (workspace), platform header |
| `--color-brand-900` | `#0F2A5F` | Page titles, selected nav item background, key figures |
| `--color-brand-800` | `#163A82` | Hover on dark surfaces, secondary emphasis |
| `--color-brand-600` | `#1D4ED8` | **Primary action** (buttons, links, focus ring, active tab underline) |
| `--color-brand-500` | `#2563EB` | Primary hover |
| `--color-brand-100` | `#DBEAFE` | Selected row / soft badge background |
| `--color-brand-50` | `#EFF6FF` | Subtle highlighted panels |
| `--color-surface` | `#FFFFFF` | Cards, tables, drawers |
| `--color-canvas` | `#F6F8FB` | App background |
| `--color-border` | `#E3E8EF` | Dividers, card borders |
| `--color-ink-900` | `#0F172A` | Primary text |
| `--color-ink-600` | `#475569` | Secondary text |
| `--color-ink-400` | `#94A3B8` | Placeholder, disabled, meta |
| Status | success `#15803D`/`#DCFCE7`, warning `#B45309`/`#FEF3C7`, danger `#B91C1C`/`#FEE2E2`, info `#1D4ED8`/`#DBEAFE`, neutral `#475569`/`#F1F5F9` | Badges, alerts, dots |

Dark blue is confined to: sidebar/nav rail, platform console header, page H1s, selected nav state, KPI numbers, primary "danger-free" emphasis. Everything else stays white/light.

## 2. Typography & spacing

- Font: `Inter` (system fallback). Sizes: 12 (meta), 13 (table body), 14 (body), 16 (section title), 20 (page title), 28 (KPI). Tabular numerals for money/bytes/time.
- Spacing scale 4px; page gutter 16 (mobile) / 24 (tablet) / 32 (desktop); card padding 16/20.
- Radius: 8px controls, 12px cards/drawers. Borders 1px `--color-border`; shadow only on floating layers (menus, dialogs, drawers).

## 3. Status vocabulary (single source: `components/feedback/status.ts`)

| Domain | Values → tone/label |
|---|---|
| Voucher | `unused` neutral "Unused" · `active` success "Active" · `expired` neutral-muted "Expired" · `disabled` danger "Disabled" |
| Payment | `pending` warning · `success` success "Paid" · `failed` danger · `abandoned` neutral |
| Fulfillment | `fulfilled` success · `paid_unfulfilled` danger "Paid, not fulfilled" · `unverified` neutral |
| Delivery | `not_requested` neutral · `pending`/`sending` info (pulsing dot) · `accepted` success "Accepted by mail server" · `failed` danger · `unknown` warning "Outcome unknown" |
| Router onboarding | `pending` neutral · `reviewed` info · `approved` info · `waiting_for_vpn` info · `vpn_failed` danger · `testing_radius` info · `radius_failed` danger · `accounting_failed` danger · `active` success · `suspended` warning |
| Deployment | `not_deployed` neutral · `deploying` info (pulse) · `deployed` success · `failed` danger |
| Operation | `pending` info · `running` info (pulse) · `succeeded` success · `failed` danger |
| Agent | `pending` warning "Awaiting approval" · `active` success · `suspended` danger |
| Subscription | `trial` info · `active` success · `expired` danger · `cancelled` neutral |
| Membership role | owner brand · manager info · staff neutral |
| Check result | passed success · failed danger · never run neutral (dashed) |

## 4. Components (in `components/ui`, headless + Tailwind; no component kit dependency)

Button (primary / secondary / ghost / danger; sm md; loading), IconButton, Input (+ prefix/suffix, error), PasswordInput (reveal), Select (native on mobile, listbox on desktop), Combobox (searchable plan/tenant pickers), Textarea, Checkbox, Switch, Badge, Card (header/body/footer), Tabs (URL-synced), Dialog, Drawer/Sheet (right on desktop, bottom on mobile), DropdownMenu, Tooltip, Toast, Skeleton, Spinner, Alert, KeyValue list, Stat card, Stepper (router onboarding), CopyField (tokens/usernames), CodeBlock (audit JSON).

Feedback patterns: `PageSkeleton` variants (table, cards, detail), `EmptyState` (icon, title, description, primary action), `ErrorState` (message, retry, "sign in again" when 401), `ConfirmDialog` (destructive variant requires typing nothing but shows consequences clearly), `InlineNotice` for permission or precondition hints (e.g. "Provisioning requires a WireGuard public key").

## 5. Layout & responsiveness

Breakpoints: `sm 640`, `md 768`, `lg 1024`, `xl 1280`, `2xl 1536`.

| Surface | < md (mobile) | md–lg (tablet) | ≥ lg (desktop) | ≥ 2xl |
|---|---|---|---|---|
| Workspace | Top bar + bottom nav (Home, Vouchers, Routers, Payments, More→drawer) | Icon rail (72px) with tooltips + top bar | Sidebar 256px (collapsible to rail) + top bar | Content max-width 1440px centred |
| Platform | Top bar (dark blue) + drawer nav | Rail | Sidebar | same |
| Agent | Bottom tabs (Home, Sell, Wallet, Vouchers, Profile) | centred 640px column | centred 720px column | same |
| Lists | RecordList cards, filters in a bottom sheet, sticky search | Table with fewer columns (priority ≤2), filters inline collapsible | Full table, inline filter bar | wider columns |
| Detail | Full page; tabs scroll horizontally | Drawer 480px | Drawer 560px or split page (routers) | — |
| Forms | Single column, sticky submit bar | 2 columns where fields pair naturally | 2 columns | — |

No horizontal overflow except intentionally scrollable tables (wrapped in `overflow-x-auto` with sticky first column).

## 6. Accessibility

Focus rings on all interactive elements (`brand-600` 2px offset), dialogs/drawers trap focus and restore, tables have `<th scope>`, status badges include text (never colour-only), touch targets ≥ 44px on mobile, `aria-live` for toasts and polling status, reduced-motion respected for pulses/skeletons, form fields wired via `Field` (label, description, error `aria-describedby`).

## 7. Copy guidelines

Operator-facing language, not model names: "Router" (not NAS), "Voucher", "Plan", "Agent", "Live sessions", "Payments", "Recovery", "Team", "Devices". Amounts always `₦12,500.00`; bytes `1.2 GB`; durations `2h 15m`; timestamps absolute with relative hint ("12 Mar 2026, 14:02 · 3 h ago").
