# Bundle report — phase 9 (performance)

Measured with `npm run build` (Vite 7, `es2022`, no sourcemaps) and
`npm run size-check` (gzip via `node:zlib`, same compression class as production
transfer). Reproduce any time:

```bash
npm run build && npm run size-check   # budgets are enforced in CI
ANALYZE=1 npm run analyze             # writes stats.html (treemap, gitignored)
```

## Budgets vs. measured

| Budget (from `06_IMPLEMENTATION_PHASES.md`, phase 9) | Target | Measured | Status |
| --- | --- | --- | --- |
| Initial JS (entry + everything it statically imports) | < 150 kB gzip | **133.5 kB gzip** | ✅ |
| Largest lazy route/feature chunk | < 120 kB gzip | **36.7 kB gzip** (`forms`) | ✅ |

## Initial JS composition (cold first paint)

| Chunk | gzip | Contents |
| --- | ---: | --- |
| `react-*.js` | 92.5 kB | react, react-dom, scheduler, react-router (+cookie parsing for auth) |
| `index-*.js` (entry) | 30.6 kB | app shell, layouts, navigation (+ the 21-entry prefetch chunk map), auth provider/guards, http client |
| `query-*.js` | 10.4 kB | TanStack Query |
| **Total** | **133.5 kB** | |

Plus `index-*.css` at **9.6 kB gzip** and a single **48.3 kB** font file (below).
The `forms` chunk (react-hook-form + zod + resolvers, 36.7 kB gzip) is **lazy** —
only routes with forms download it. Every one of the 139 lazy chunks is a page
or a small shared module; route chunks are 1.3–22.5 kB gzip each (largest:
`RouterDetailPage` at 7.7 kB — the 36.7 kB "largest lazy chunk" is the shared
`forms` vendor group, still 3× under budget).

## What changed in phase 9

| Metric | Before | After | Delta |
| --- | ---: | ---: | --- |
| Initial JS | 132.4 kB gzip | 133.5 kB gzip | +1.1 kB (nav-prefetch chunk map, error reporter) |
| Font payload | 7 woff2 files, 218.5 kB | **1 woff2 file, 48.3 kB** | −78 % |
| CSS | 9.9 kB gzip | 9.6 kB gzip | −0.4 kB |
| Lazy chunks | 134 | 139 | +5 (prefetch/query registry shared chunk, re-splitting) |

### Font fix (subsetting *and* a real bug)

`main.tsx` used to import `@fontsource-variable/inter`, which emits **all seven
unicode subsets** (cyrillic, cyrillic-ext, greek, greek-ext, vietnamese,
latin-ext, latin — 218.5 kB of woff2) and registers the family as
`'Inter Variable'`. The design tokens referenced `'Inter'` — so the font was
**downloaded but never applied**; every screen actually rendered the system
stack.

Phase 9 replaces it with a single latin-subset `@font-face` (family `'Inter'`,
`font-weight: 100 900`, `font-display: swap`, `unicode-range` latin) pointing at
the package's `inter-latin-wght-normal.woff2` (48.3 kB). Inter now actually
renders, and the payload drops by 170 kB. ₦ (U+20A6, naira sign) is outside the
latin subset and intentionally falls back to the system stack — metrics are
close enough that money strings remain visually consistent.

### Route/feature code-splitting (review)

Confirmed unchanged and correct: every page in `src/app/router/index.tsx` is a
`lazy()` import wrapped in `lazyRoute` (Suspense + `RouteFallback`), one chunk
per page; `manualChunks` pins the `react` / `query` / `forms` vendor groups.
The dev-only UI gallery is behind `import.meta.env.DEV` and never ships.

### Nav-hover prefetch (new)

`src/app/navigation/prefetch.ts` + `routeQueries.ts`: hovering or keyboard-
focusing any nav item preloads its route chunk (identical dynamic-import
specifiers, so chunks dedupe); the top routes additionally prefetch the queries
the page fires on mount. The query registry is itself lazy, keeping feature
query modules out of the entry chunk. See `QUERY_AUDIT.md` for the no-duplicate-
fetch reasoning.

### Image-free UI

Confirmed: no `<img>`, no `background-image`, no `url()` asset references in
`src/` — the UI is pure CSS/SVG (inline lucide icons, one 377-byte
`favicon.svg`). Nothing to lazy-load or optimize there.

## Ongoing enforcement

`npm run size-check` (`scripts/check-bundle-size.mjs`) parses `dist/index.html`,
walks the static-import graph to separate initial from lazy chunks, gzips
everything and fails the build if either budget is exceeded. CI runs it on
every push/PR (`frontend/.github/workflows/ci.yml`). Current headroom: ~17 kB
initial, ~83 kB per lazy chunk.
