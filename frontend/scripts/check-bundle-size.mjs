#!/usr/bin/env node
/**
 * Bundle budget check (phase 9 deliverable, wired into CI in phase 11).
 *
 * Budgets from analysis/06_IMPLEMENTATION_PHASES.md — phase 9:
 *   - initial JS (entry + everything it statically imports): < 150 kB gzip
 *   - largest lazy route/feature chunk:                     < 120 kB gzip
 *
 * "Initial" = the entry script(s) in dist/index.html plus every chunk reachable
 * from them through static imports — what a cold first paint downloads before
 * any route chunk loads. Everything else in dist/assets is lazy.
 */
import { existsSync, readdirSync, readFileSync } from 'node:fs';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { gzipSync } from 'node:zlib';

const distDir = fileURLToPath(new URL('../dist/', import.meta.url));
const assetsDir = join(distDir, 'assets');

const INITIAL_JS_BUDGET_BYTES = 150 * 1000;
const LAZY_CHUNK_BUDGET_BYTES = 120 * 1000;

const fmt = (bytes) => `${(bytes / 1000).toFixed(1)} kB`;

if (!existsSync(join(distDir, 'index.html'))) {
  console.error('dist/index.html not found — run `npm run build` first.');
  process.exit(1);
}

const html = readFileSync(join(distDir, 'index.html'), 'utf8');
const entryScripts = [...html.matchAll(/<script[^>]+src="\.?\/?(assets\/[^"]+\.js)"/g)].map((m) =>
  m[1].replace(/^assets\//, ''),
);
if (entryScripts.length === 0) {
  console.error('No entry script found in dist/index.html.');
  process.exit(1);
}

const allJs = readdirSync(assetsDir).filter((file) => file.endsWith('.js'));

/** Static imports of a built chunk (rollup emits `from"./x.js"` / `import"./x.js"`). */
function staticImports(file) {
  const source = readFileSync(join(assetsDir, file), 'utf8');
  const deps = new Set();
  for (const match of source.matchAll(/(?:from|import)\s*"\.\/([^"]+\.js)"/g)) deps.add(match[1]);
  return deps;
}

const initial = new Set();
const queue = [...entryScripts];
while (queue.length > 0) {
  const file = queue.pop();
  if (initial.has(file)) continue;
  initial.add(file);
  for (const dep of staticImports(file)) if (!initial.has(dep)) queue.push(dep);
}

const gzipSize = (file) => gzipSync(readFileSync(join(assetsDir, file))).length;
const initialRows = [...initial]
  .map((file) => ({ file, gzip: gzipSize(file) }))
  .sort((a, b) => b.gzip - a.gzip);
const lazyRows = allJs
  .filter((file) => !initial.has(file))
  .map((file) => ({ file, gzip: gzipSize(file) }))
  .sort((a, b) => b.gzip - a.gzip);
const initialTotal = initialRows.reduce((sum, row) => sum + row.gzip, 0);
const largestLazy = lazyRows[0] ?? { file: '—', gzip: 0 };

console.log('Initial JS (cold first paint, gzip):');
for (const row of initialRows) console.log(`  ${fmt(row.gzip).padStart(8)}  ${row.file}`);
console.log(`  ${fmt(initialTotal).padStart(8)}  TOTAL (${initialRows.length} chunks)`);
console.log('');
console.log(
  `Lazy chunks: ${lazyRows.length} — largest ${fmt(largestLazy.gzip)} (${largestLazy.file})`,
);
console.log('');
console.log('Other first-paint assets (gzip):');
for (const file of readdirSync(assetsDir).filter((f) => /\.(css|woff2?|svg)$/.test(f))) {
  console.log(`  ${fmt(gzipSize(file)).padStart(8)}  ${file}`);
}
console.log('');

let ok = true;
if (initialTotal > INITIAL_JS_BUDGET_BYTES) {
  ok = false;
  console.error(
    `FAIL: initial JS ${fmt(initialTotal)} exceeds ${fmt(INITIAL_JS_BUDGET_BYTES)} budget`,
  );
} else {
  console.log(
    `PASS: initial JS ${fmt(initialTotal)} within ${fmt(INITIAL_JS_BUDGET_BYTES)} budget`,
  );
}
if (largestLazy.gzip > LAZY_CHUNK_BUDGET_BYTES) {
  ok = false;
  console.error(
    `FAIL: largest lazy chunk ${fmt(largestLazy.gzip)} exceeds ${fmt(LAZY_CHUNK_BUDGET_BYTES)} budget`,
  );
} else {
  console.log(
    `PASS: largest lazy chunk ${fmt(largestLazy.gzip)} within ${fmt(LAZY_CHUNK_BUDGET_BYTES)} budget`,
  );
}

process.exit(ok ? 0 : 1);
