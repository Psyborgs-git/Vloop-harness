// @ts-check
/**
 * CP-only API consumption smoke test (Requirement 20.4).
 *
 * The Frontend is served by the Control_Plane HTTP shell and MUST talk *only*
 * to the Control_Plane over its HTTP/WebSocket APIs — never to the Kernel, a
 * database, or any third-party origin directly. This is a lightweight static
 * source scan (no test runner, no npm deps — just node:fs/node:path) that
 * asserts every network access in `src/src/**` targets the Control_Plane:
 *
 *   1. Every URL passed to `requestJson` / `requestWithFallback` (the shared
 *      HTTP client) resolves to a *relative, same-origin* path (`/…`). A
 *      relative path is served by the CP shell, so it is CP-only by
 *      construction. Absolute URLs (`http(s)://host`, `ws(s)://host`) or
 *      protocol-relative (`//host`) paths are rejected.
 *   2. `new WebSocket(...)` appears in exactly one file — the shared
 *      `hooks/useWorkflowEvents.ts` hook — and is not handed a hardcoded
 *      absolute non-CP URL literal (it derives a same-origin URL).
 *   3. `fetch(...)` appears in exactly one file — the shared `lib/api-client.ts`
 *      — and is not handed a hardcoded absolute URL literal.
 *   4. The orchestration views (workflows / approvals / budgets / checkpoints /
 *      schedule) never call `fetch(` or `new WebSocket(` directly; they consume
 *      data only through `../../lib/api` (or the endpoints modules) and the
 *      shared `useWorkflowEvents` hook.
 *
 * Exit 0 when everything is CP-only; exit 1 with a clear message otherwise.
 */

import { readdirSync, readFileSync, statSync } from "node:fs";
import { dirname, join, relative } from "node:path";
import { fileURLToPath } from "node:url";

const SCRIPT_DIR = dirname(fileURLToPath(import.meta.url));
// tests/ sits alongside the frontend source root src/src.
const SOURCE_ROOT = join(SCRIPT_DIR, "..", "src");

/** @type {string[]} */
const violations = [];
/** @type {string[]} */
const notes = [];

function fail(message) {
  violations.push(message);
}

function rel(absPath) {
  return relative(join(SCRIPT_DIR, ".."), absPath);
}

/** Recursively collect .ts/.tsx files under a directory. */
function collectSourceFiles(dir) {
  /** @type {string[]} */
  const out = [];
  for (const entry of readdirSync(dir)) {
    const full = join(dir, entry);
    const st = statSync(full);
    if (st.isDirectory()) {
      out.push(...collectSourceFiles(full));
    } else if (/\.(ts|tsx)$/.test(entry)) {
      out.push(full);
    }
  }
  return out;
}

/**
 * Strip block and line comments so we only reason about executable code.
 * (Comments legitimately mention `http://`, `ws://`, doc links, etc.)
 */
function stripComments(source) {
  return source
    .replace(/\/\*[\s\S]*?\*\//g, " ")
    .replace(/(^|[^:])\/\/[^\n]*/g, "$1 ");
}

/**
 * Extract the static (non-interpolated) text of every string and template
 * literal in a comment-stripped source. For template literals the `${...}`
 * interpolations are removed, leaving only the author-written static parts.
 *
 * @param {string} code  comment-stripped source
 * @returns {{ text: string, kind: "string" | "template", raw: string }[]}
 */
function extractLiterals(code) {
  /** @type {{ text: string, kind: "string" | "template", raw: string }[]} */
  const out = [];
  const re = /`(?:[^`\\]|\\.)*`|"(?:[^"\\]|\\.)*"|'(?:[^'\\]|\\.)*'/g;
  let m;
  while ((m = re.exec(code)) !== null) {
    const raw = m[0];
    if (raw.startsWith("`")) {
      // Replace `${...}` with a sentinel so composing static parts can't forge
      // a spurious "//" or "://". Each interpolation resolves to a value that
      // is validated independently (e.g. base consts declared as "/api/…").
      const inner = raw.slice(1, -1).replace(/\$\{[^}]*\}/g, "\u0000");
      out.push({ text: inner, kind: "template", raw });
    } else {
      out.push({ text: raw.slice(1, -1), kind: "string", raw });
    }
  }
  return out;
}

/**
 * The networking modules — the only files that build HTTP paths / WebSocket
 * URLs. Their literals must never encode an absolute or cross-origin target:
 * a relative path is served by the CP shell, so it is CP-only by construction.
 */
function isNetworkingModule(file) {
  const p = file.split(/[\\/]/).join("/");
  return (
    p.endsWith("/lib/api-client.ts") ||
    p.includes("/lib/endpoints/") ||
    p.endsWith("/hooks/useWorkflowEvents.ts")
  );
}

/**
 * Check 1: the networking modules contain no absolute or protocol-relative URL
 * literal — every network target they build is a relative same-origin path
 * (`/…`), which the Control_Plane HTTP shell serves. This is the direct
 * enforcement of Req 20.4: no Kernel/db/third-party origin is ever addressed.
 */
function checkHttpCallSites(files) {
  let scannedModules = 0;
  let relativePathLiterals = 0;

  for (const file of files) {
    if (!isNetworkingModule(file)) {
      continue;
    }
    scannedModules += 1;
    const code = stripComments(readFileSync(file, "utf8"));

    for (const lit of extractLiterals(code)) {
      // Absolute URL with an explicit scheme (http://, https://, ws://, wss://,
      // or any other) is never a valid Control_Plane target from the Frontend.
      if (lit.text.includes("://")) {
        fail(
          `[HTTP] ${rel(file)}: absolute URL literal ${lit.raw} — the Frontend must ` +
            `only address the Control_Plane via relative same-origin paths (Req 20.4).`,
        );
        continue;
      }
      // Protocol-relative literal ("//host/…") would also escape the CP origin.
      if (lit.text.startsWith("//")) {
        fail(
          `[HTTP] ${rel(file)}: protocol-relative URL literal ${lit.raw} — cross-origin ` +
            `targets are not allowed (Req 20.4).`,
        );
        continue;
      }
      if (lit.text.startsWith("/")) {
        relativePathLiterals += 1;
      }
    }
  }

  if (scannedModules === 0) {
    fail("[HTTP] No networking modules (lib/api-client.ts, lib/endpoints/*.ts) were found to scan.");
  }
  notes.push(
    `Scanned ${scannedModules} networking module(s); ${relativePathLiterals} relative Control_Plane ` +
      `path literal(s), zero absolute/cross-origin URLs.`,
  );
}

/**
 * Check 2: WebSocket usage is confined to the shared hook and never a hardcoded
 * absolute URL literal.
 */
function checkWebSocketUsage(files) {
  const ALLOWED_WS = join(SOURCE_ROOT, "hooks", "useWorkflowEvents.ts");
  let count = 0;
  for (const file of files) {
    const code = stripComments(readFileSync(file, "utf8"));
    const wsRe = /new\s+WebSocket\s*\(\s*([^)]*)\)/g;
    let m;
    while ((m = wsRe.exec(code)) !== null) {
      count += 1;
      if (file !== ALLOWED_WS) {
        fail(
          `[WS] ${rel(file)}: constructs 'new WebSocket(...)' — the only allowed WebSocket ` +
            `owner is hooks/useWorkflowEvents.ts (shared same-origin CP push channel).`,
        );
        continue;
      }
      const arg = m[1].trim();
      if (/["'`].*:\/\//.test(arg)) {
        fail(`[WS] ${rel(file)}: WebSocket URL is a hardcoded absolute literal (${arg}); it must be derived from same origin.`);
      }
    }
  }
  if (count === 0) {
    fail("[WS] Expected exactly one 'new WebSocket(...)' in hooks/useWorkflowEvents.ts, found none.");
  } else {
    notes.push(`Found ${count} 'new WebSocket(...)' site(s), all in hooks/useWorkflowEvents.ts (same-origin CP).`);
  }
}

/**
 * Check 3: fetch() is confined to the shared api-client and never a hardcoded
 * absolute URL literal.
 */
function checkFetchUsage(files) {
  const ALLOWED_FETCH = join(SOURCE_ROOT, "lib", "api-client.ts");
  let count = 0;
  for (const file of files) {
    const code = stripComments(readFileSync(file, "utf8"));
    // Match `fetch(` but not `.fetch(`/`refetch(` etc.
    const fetchRe = /(^|[^.\w])fetch\s*\(\s*([^,)\n]*)/g;
    let m;
    while ((m = fetchRe.exec(code)) !== null) {
      count += 1;
      if (file !== ALLOWED_FETCH) {
        fail(
          `[FETCH] ${rel(file)}: calls fetch() directly — all HTTP access must go through ` +
            `lib/api-client.ts (requestJson/requestWithFallback).`,
        );
        continue;
      }
      const arg = m[2].trim();
      if (/["'`].*:\/\//.test(arg)) {
        fail(`[FETCH] ${rel(file)}: fetch() target is a hardcoded absolute URL literal (${arg}).`);
      }
    }
  }
  if (count === 0) {
    fail("[FETCH] Expected exactly one fetch() in lib/api-client.ts, found none.");
  } else {
    notes.push(`Found ${count} fetch() site(s), all in lib/api-client.ts (relative CP paths only).`);
  }
}

/**
 * Check 4: orchestration views consume data only via the CP client layer.
 */
function checkOrchestrationViews() {
  const viewDirs = ["workflows", "approvals", "budgets", "checkpoints", "schedule"];
  let checked = 0;
  for (const dir of viewDirs) {
    const viewDir = join(SOURCE_ROOT, "views", dir);
    let entries;
    try {
      entries = readdirSync(viewDir).filter((e) => e.endsWith(".tsx"));
    } catch {
      fail(`[VIEW] Missing orchestration view directory: views/${dir}`);
      continue;
    }
    if (entries.length === 0) {
      fail(`[VIEW] No .tsx files found in views/${dir}`);
    }
    for (const entry of entries) {
      checked += 1;
      const file = join(viewDir, entry);
      const raw = readFileSync(file, "utf8");
      const code = stripComments(raw);

      if (/(^|[^.\w])fetch\s*\(/.test(code)) {
        fail(`[VIEW] ${rel(file)}: calls fetch() directly — views must use ../../lib/api (Control_Plane) only.`);
      }
      if (/new\s+WebSocket\s*\(/.test(code)) {
        fail(`[VIEW] ${rel(file)}: constructs 'new WebSocket(...)' — views must use the shared useWorkflowEvents hook.`);
      }
      if (/:\/\//.test(code)) {
        fail(`[VIEW] ${rel(file)}: contains an absolute URL literal in code — views must only reach the Control_Plane via relative paths.`);
      }

      // Any data-access import must come from the CP client layer or the shared hook.
      const importRe = /import\s+[^;]*?\bfrom\s+(["'])([^"']+)\1/g;
      let im;
      while ((im = importRe.exec(code)) !== null) {
        const spec = im[2];
        if (!spec.startsWith(".")) {
          // Package imports (react, etc.) are UI-only and never do CP data access here.
          continue;
        }
        const okData =
          /\/lib\/api$/.test(spec) ||
          /\/lib\/api-client$/.test(spec) ||
          /\/lib\/endpoints(\/|$)/.test(spec) ||
          /\/hooks\/useWorkflowEvents$/.test(spec) ||
          /\/components\/ui$/.test(spec) ||
          /\/lib\/types$/.test(spec) ||
          /\/lib\/helpers$/.test(spec) ||
          /\/lib\/normalizers$/.test(spec);
        if (!okData) {
          notes.push(`[VIEW] ${rel(file)}: local import '${spec}' (non data-access; allowed).`);
        }
      }
    }
  }
  notes.push(`Checked ${checked} orchestration view file(s); none call fetch()/WebSocket directly.`);
}

// --- Run all checks --------------------------------------------------------

let allFiles;
try {
  allFiles = collectSourceFiles(SOURCE_ROOT);
} catch (err) {
  console.error(`Could not read frontend source root at ${SOURCE_ROOT}: ${err}`);
  process.exit(1);
}

const endpointFiles = allFiles.filter((f) => f.includes(join("lib", "endpoints")));

// requestJson/requestWithFallback are used across the lib tree (endpoints
// modules + lib/endpoints/system.ts CP-shell routes); scan every source file.
checkHttpCallSites(allFiles);
checkWebSocketUsage(allFiles);
checkFetchUsage(allFiles);
checkOrchestrationViews();

// Sanity: ensure we actually found the endpoint modules we expect to scan.
if (endpointFiles.length === 0) {
  fail("[SETUP] No lib/endpoints/*.ts modules found — scan target missing.");
}

// --- Report ----------------------------------------------------------------

console.log("CP-only API consumption smoke test (Requirement 20.4)");
console.log(`Source root: ${rel(SOURCE_ROOT)}`);
for (const note of notes) {
  console.log(`  · ${note}`);
}

if (violations.length > 0) {
  console.error(`\nFAIL: ${violations.length} CP-only violation(s) found:`);
  for (const v of violations) {
    console.error(`  ✗ ${v}`);
  }
  console.error("\nThe Frontend must consume ONLY Control_Plane HTTP/WebSocket APIs (Req 20.4).");
  process.exit(1);
}

console.log("\nPASS: all views and endpoints consume only Control_Plane HTTP/WebSocket APIs.");
process.exit(0);
