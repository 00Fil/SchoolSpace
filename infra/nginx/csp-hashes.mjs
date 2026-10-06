// Calcola gli hash CSP ('sha256-...') degli <script> inline di index.html, così la CSP
// non richiede 'unsafe-inline' anche se il frontend mantiene lo script del tema.
import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";

const html = readFileSync(process.argv[2] ?? "dist/index.html", "utf8");
const hashes = [];
for (const m of html.matchAll(/<script(?![^>]*\bsrc=)[^>]*>([\s\S]*?)<\/script>/gi)) {
  hashes.push(`'sha256-${createHash("sha256").update(m[1], "utf8").digest("base64")}'`);
}
process.stdout.write(hashes.join(" "));
