#!/usr/bin/env node
/**
 * Test unitari e di componente senza dipendenze aggiuntive (GAP-G06): ogni file
 * `tests/*.test.ts(x)` viene compilato con esbuild (già presente come dipendenza di Vite)
 * ed eseguito con `node --test`. I componenti si verificano con react-dom/server.
 * Il DOM minimo necessario all'import dei moduli è in tests/setup.ts.
 */
import { build } from "esbuild";
import { mkdtempSync, readdirSync, readFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import { spawnSync } from "node:child_process";

const root = resolve(import.meta.dirname, "..");
const filter = process.argv[2] || "";
const files = readdirSync(join(root, "tests")).filter((f) => /\.test\.tsx?$/.test(f) && f.includes(filter)).sort();
const out = mkdtempSync(join(tmpdir(), "ui-tests-"));
const raw = {
  name: "raw-and-css",
  setup(b) {
    b.onResolve({ filter: /\?raw$/ }, (a) => ({ path: resolve(a.resolveDir, a.path.replace(/\?raw$/, "")), namespace: "raw" }));
    b.onLoad({ filter: /.*/, namespace: "raw" }, (a) => ({ contents: readFileSync(a.path, "utf8"), loader: "text" }));
    b.onResolve({ filter: /\.css$/ }, (a) => ({ path: a.path, namespace: "css" }));
    b.onLoad({ filter: /.*/, namespace: "css" }, () => ({ contents: "", loader: "js" }));
  },
};
try {
  await build({
    entryPoints: files.map((f) => join(root, "tests", f)), outdir: out, bundle: true, platform: "node", format: "esm",
    jsx: "automatic", target: "node20", sourcemap: "inline", logLevel: "error", plugins: [raw],
    inject: [join(root, "tests", "setup.ts")], outExtension: { ".js": ".mjs" },
    banner: { js: "import { createRequire as __cr } from 'node:module'; const require = __cr(import.meta.url);" },
  });
  const r = spawnSync(process.execPath, ["--test", "--test-reporter=spec", ...files.map((f) => join(out, f.replace(/\.tsx?$/, ".mjs")))], { stdio: "inherit", env: { ...process.env, TZ: "UTC" } });
  process.exitCode = r.status ?? 1;
} finally {
  rmSync(out, { recursive: true, force: true });
}
