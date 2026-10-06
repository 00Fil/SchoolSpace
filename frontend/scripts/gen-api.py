#!/usr/bin/env python3
"""Genera frontend/src/api/schema.gen.ts da contracts/openapi.yaml (GAP-G05).

Uso: python frontend/scripts/gen-api.py [--check]
--check esce con codice 1 se il file generato non è aggiornato (da usare in CI).
Dipende solo da PyYAML (già in backend/requirements-dev.txt). Nessuna rete.
Copre il sottoinsieme JSON Schema usato dal contratto: $ref, type (anche lista),
enum, const, properties/required, additionalProperties, items, allOf/oneOf/anyOf.
"""

import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
SPEC = ROOT / "contracts" / "openapi.yaml"
OUT = ROOT / "frontend" / "src" / "api" / "schema.gen.ts"
METHODS = ("get", "post", "put", "patch", "delete")
IDENT = re.compile(r"^[A-Za-z_$][A-Za-z0-9_$]*$")


def key(name):
    return name if IDENT.match(name) else repr(name).replace("'", '"')


def lit(value):
    if isinstance(value, bool):
        return "true" if value else "false"
    if value is None:
        return "null"
    if isinstance(value, (int, float)):
        return str(value)
    return '"' + str(value).replace("\\", "\\\\").replace('"', '\\"') + '"'


def ts(schema, depth=0):
    if not isinstance(schema, dict) or not schema:
        return "unknown"
    if "$ref" in schema:
        return "S." + schema["$ref"].rsplit("/", 1)[-1]
    if "const" in schema:
        return lit(schema["const"])
    if "enum" in schema:
        out = " | ".join(lit(v) for v in schema["enum"])
        return f"({out})" if schema.get("nullable") else out
    for combo, sep in (("allOf", " & "), ("oneOf", " | "), ("anyOf", " | ")):
        if combo in schema:
            parts = [ts(s, depth) for s in schema[combo]]
            rest = {k: v for k, v in schema.items() if k != combo}
            if rest.get("type") or rest.get("properties"):
                parts.append(ts(rest, depth))
            return "(" + sep.join(parts) + ")"
    kind = schema.get("type")
    if isinstance(kind, list):
        return " | ".join(ts({**schema, "type": k}, depth) for k in kind)
    nullable = " | null" if schema.get("nullable") else ""
    if kind in ("integer", "number"):
        return "number" + nullable
    if kind == "string":
        return "string" + nullable
    if kind == "boolean":
        return "boolean" + nullable
    if kind == "null":
        return "null"
    if kind == "array":
        return f"Array<{ts(schema.get('items', {}), depth)}>" + nullable
    if kind == "object" or "properties" in schema:
        props = schema.get("properties") or {}
        required = set(schema.get("required") or [])
        pad = "  " * (depth + 1)
        lines = [
            f"{pad}{key(name)}{'' if name in required else '?'}: {ts(sub, depth + 1)};"
            for name, sub in props.items()
        ]
        extra = schema.get("additionalProperties")
        if isinstance(extra, dict):
            lines.append(f"{pad}[key: string]: {ts(extra, depth + 1)};")
        elif extra is not False and not props:
            lines.append(f"{pad}[key: string]: unknown;")
        if not lines:
            return "Record<string, never>" + nullable
        return "{\n" + "\n".join(lines) + "\n" + "  " * depth + "}" + nullable
    return "unknown"


def body_schema(container):
    content = (container or {}).get("content") or {}
    media = content.get("application/json")
    return media.get("schema") if media else None


def success(responses):
    for code in sorted(responses or {}):
        if str(code).startswith("2"):
            schema = body_schema(responses[code])
            return ts(schema, 3) if schema else "unknown"
    return "unknown"


def query_type(params):
    rows = [p for p in params if p.get("in") == "query"]
    if not rows:
        return "Record<string, never>"
    inner = "; ".join(
        f"{key(p['name'])}{'' if p.get('required') else '?'}: {ts(p.get('schema', {}), 3)}"
        for p in rows
    )
    return "{ " + inner + " }"


def generate(spec):
    out = [
        "/* eslint-disable */",
        "// GENERATO da frontend/scripts/gen-api.py a partire da contracts/openapi.yaml.",
        "// Non modificare a mano: rigenera con `npm run gen:api` (verifica in CI con `npm run check:api`).",
        f"// Contratto: {spec['info']['title']} {spec['info']['version']}",
        "",
        "export namespace S {",
    ]
    for name, schema in spec["components"]["schemas"].items():
        out.append(f"  export type {name} = {ts(schema, 1)};")
    out += ["}", "", "export interface Paths {"]
    ops = []
    for path, item in spec["paths"].items():
        common = item.get("parameters") or []
        out.append(f"  {lit(path)}: {{")
        for method in METHODS:
            if method not in item:
                continue
            op = item[method]
            params = common + (op.get("parameters") or [])
            body = body_schema(op.get("requestBody"))
            out.append(f"    {method}: {{")
            out.append(f"      query: {query_type(params)};")
            out.append(f"      body: {ts(body, 3) if body else 'never'};")
            out.append(f"      response: {success(op.get('responses'))};")
            out.append("    };")
            if op.get("operationId"):
                ops.append((op["operationId"], method.upper(), path))
        out.append("  };")
    out += ["}", "", "export const OPERATIONS = {"]
    for op_id, method, path in sorted(ops):
        out.append(f"  {key(op_id)}: [{lit(method)}, {lit(path)}],")
    out += [
        "} as const;",
        "",
        "export type PathsWith<M extends string> = { [P in keyof Paths]: M extends keyof Paths[P] ? P : never }[keyof Paths];",
        "",
    ]
    return "\n".join(out)


def main():
    text = generate(yaml.safe_load(SPEC.read_text()))
    if "--check" in sys.argv:
        if not OUT.exists() or OUT.read_text() != text:
            print(
                "schema.gen.ts non aggiornato: esegui `npm run gen:api`",
                file=sys.stderr,
            )
            return 1
        print("schema.gen.ts aggiornato")
        return 0
    OUT.write_text(text)
    print(f"Scritto {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
