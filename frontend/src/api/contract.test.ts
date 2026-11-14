/**
 * ABB-29: backend OpenAPI contract versus the hand-written frontend types (`types.ts`).
 *
 * The OpenAPI document is produced by the backend (`scripts/export_openapi.py`) and passed in the
 * `OPENAPI_JSON` environment variable (`make contract` and the `web-build` CI job do this). Without it
 * the test is skipped, so a plain `npm test` stays offline and fast.
 *
 * Every exported type of `types.ts` whose name is also an OpenAPI schema is compared field by field.
 * A type is a REQUEST when its name says so (Create, Update, Patch, Request, Change, Grant, Input, ...);
 * everything else is a RESPONSE. The rules are the ones that break a user at runtime:
 *   both    - a frontend field the backend does not define; a different primitive kind.
 *   response- a non-null frontend field the backend may send as null; a backend enum value missing from a frontend union.
 *   request - an optional/nullable frontend field the backend requires or rejects; a frontend union value
 *             the backend does not accept.
 * Known, documented mismatches live in KNOWN_DRIFT: the test fails on any new drift AND on a stale entry,
 * so the list can only shrink once the frontend is fixed or generated types replace types.ts (ABB-02 A7).
 */
import { readdirSync, readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import ts from 'typescript';
import { describe, expect, it } from 'vitest';

type Json = any; // OpenAPI documents are untyped JSON by nature.

const OPENAPI_PATH = process.env.OPENAPI_JSON;
const TYPES_FILE = resolve(__dirname, 'types.ts');
const REQUEST_NAME = /(Create|Created|Update|Patch|Request|Change|Grant|Input|Edit|Decision|Login|Register)$/;

/** type.path -> why it is accepted for now. Keep entries precise and remove them when fixed. */
export const KNOWN_DRIFT: Record<string, string> = {};

/**
 * Same name, different thing: these frontend types describe the legacy untyped endpoints
 * (`GET /api/literature`, `GET /api/rotations/demo`), not the v1 schemas of the same name. They are not
 * in the OpenAPI document with that shape, so there is nothing to compare until those endpoints are typed.
 */
export const NOT_COMPARED: Record<string, string> = {
  Paper: 'legacy GET /api/literature result; the OpenAPI Paper is the v1 evidence paper',
  Rotation: 'legacy GET /api/rotations/demo item; the OpenAPI Rotation is the v1 rotation contract',
};

class Checker {
  readonly problems: string[] = [];
  constructor(private readonly schemas: Record<string, Json>, private readonly tc: ts.TypeChecker) {}

  private deref(schema: Json): Json {
    let s = schema;
    while (s && s.$ref) s = this.schemas[s.$ref.split('/').pop() as string];
    return s ?? {};
  }

  /** Strips null from anyOf/oneOf/type lists. */
  private unwrap(schemaIn: Json): { schema: Json; nullable: boolean } {
    const schema = this.deref(schemaIn);
    const variants: Json[] | undefined = schema.anyOf ?? schema.oneOf;
    if (variants) {
      const rest = variants.filter((v) => v.type !== 'null');
      const nullable = rest.length !== variants.length;
      if (rest.length === 1) return { schema: this.unwrap(rest[0]).schema, nullable };
      return { schema: { ...schema, anyOf: rest }, nullable };
    }
    if (Array.isArray(schema.type)) {
      const rest = schema.type.filter((t: string) => t !== 'null');
      return { schema: { ...schema, type: rest.length === 1 ? rest[0] : rest }, nullable: rest.length !== schema.type.length };
    }
    if (schema.allOf?.length === 1) return this.unwrap(schema.allOf[0]);
    return { schema, nullable: false };
  }

  private enumValues(schema: Json): unknown[] | null {
    if (schema.enum) return schema.enum;
    if ('const' in schema) return [schema.const];
    return null;
  }

  private split(type: ts.Type): { parts: ts.Type[]; nullable: boolean } {
    const all = type.isUnion() ? type.types : [type];
    const nullable = all.some((t) => t.flags & (ts.TypeFlags.Null | ts.TypeFlags.Undefined));
    const parts = all.filter((t) => !(t.flags & (ts.TypeFlags.Null | ts.TypeFlags.Undefined | ts.TypeFlags.Void)));
    // `boolean` is a union of true | false: fold it back.
    const bools = parts.filter((t) => t.flags & ts.TypeFlags.BooleanLiteral);
    const folded = parts.filter((t) => !(t.flags & ts.TypeFlags.BooleanLiteral));
    if (bools.length) folded.push(this.tc.getBooleanType());
    return { parts: folded, nullable };
  }

  private kind(type: ts.Type): string {
    const f = type.flags;
    if (f & (ts.TypeFlags.Any | ts.TypeFlags.Unknown)) return 'any';
    if (f & ts.TypeFlags.StringLike) return 'string';
    if (f & ts.TypeFlags.NumberLike) return 'number';
    if (f & ts.TypeFlags.BooleanLike) return 'boolean';
    if (this.tc.isArrayType(type) || this.tc.isTupleType(type)) return 'array';
    if (f & ts.TypeFlags.Object) return 'object';
    return 'other';
  }

  private literals(parts: ts.Type[]): unknown[] | null {
    const out: unknown[] = [];
    for (const t of parts) {
      if (t.isStringLiteral()) out.push(t.value);
      else if (t.isNumberLiteral()) out.push(t.value);
      else if (t.flags & ts.TypeFlags.BooleanLiteral) out.push((t as any).intrinsicName === 'true');
      else return null; // plain string/number/object among the parts: not a closed set
    }
    return out;
  }

  compareProp(where: string, request: boolean, tsProp: ts.Symbol, decl: ts.Node, schemaProp: Json | undefined,
              requiredByBackend: boolean) {
    if (!schemaProp) {
      this.problems.push(`${where}: the frontend declares a field the backend does not define`);
      return;
    }
    const optional = (tsProp.flags & ts.SymbolFlags.Optional) !== 0;
    const type = this.tc.getTypeOfSymbolAtLocation(tsProp, decl);
    const { schema, nullable: backendNullable } = this.unwrap(schemaProp);
    const { nullable: tsNullable } = this.split(type);
    if (request) {
      if (requiredByBackend && optional) this.problems.push(`${where}: optional in the frontend but required by the backend`);
      if (tsNullable && !optional && !backendNullable) this.problems.push(`${where}: nullable in the frontend but the backend does not accept null`);
      if (optional && !requiredByBackend) { /* fine */ }
    } else {
      if (!tsNullable && backendNullable) this.problems.push(`${where}: not nullable in the frontend but the backend may send null`);
    }
    this.compareType(where, request, type, schema);
  }

  compareType(where: string, request: boolean, type: ts.Type, schemaIn: Json) {
    const { schema } = this.unwrap(schemaIn);
    const { parts } = this.split(type);
    if (!parts.length) return;
    const wanted = this.enumValues(schema);
    const lits = this.literals(parts);
    if (wanted && lits) {
      const missing = request ? lits.filter((v) => !wanted.includes(v)) : wanted.filter((v) => !lits.includes(v));
      if (missing.length) {
        this.problems.push(`${where}: ${request ? 'frontend values the backend rejects' : 'backend values missing in the frontend'}: ${missing.join(', ')}`);
      }
      return;
    }
    if (parts.length > 1 && !lits) return; // real unions of object types: compared through their own names
    const part = parts[0];
    const k = this.kind(part);
    if (k === 'any' || k === 'other') return;
    const st = schema.type;
    const want = st === 'integer' ? 'number' : st;
    if (schema.anyOf || schema.allOf || !st) return;
    if (want === 'array') {
      if (k !== 'array') return void this.problems.push(`${where}: backend sends an array, frontend declares ${k}`);
      const el = this.tc.getTypeArguments(part as ts.TypeReference)[0];
      if (el && schema.items) this.compareType(`${where}[]`, request, el, schema.items);
      return;
    }
    if (want === 'object') {
      if (k !== 'object') return void this.problems.push(`${where}: backend sends an object, frontend declares ${k}`);
      if (schema.properties) this.compareObject(where, request, part, schema);
      return;
    }
    if (k !== want) this.problems.push(`${where}: backend type ${want}, frontend ${k}`);
  }

  compareObject(where: string, request: boolean, type: ts.Type, schema: Json) {
    const required: string[] = schema.required ?? [];
    for (const prop of this.tc.getPropertiesOfType(type)) {
      const decl = prop.valueDeclaration ?? prop.declarations?.[0];
      if (!decl) continue;
      this.compareProp(`${where}.${prop.name}`, request, prop, decl, schema.properties?.[prop.name], required.includes(prop.name));
    }
  }
}

describe.skipIf(!OPENAPI_PATH)('OpenAPI contract versus frontend/src/api/types.ts', () => {
  const doc: Json = OPENAPI_PATH ? JSON.parse(readFileSync(OPENAPI_PATH, 'utf8')) : { components: { schemas: {} } };
  const schemas: Record<string, Json> = doc.components.schemas;
  const program = ts.createProgram([TYPES_FILE], {
    strict: true, target: ts.ScriptTarget.ES2022, moduleResolution: ts.ModuleResolutionKind.Bundler,
    module: ts.ModuleKind.ESNext, skipLibCheck: true, noEmit: true,
  });
  const tc = program.getTypeChecker();
  const source = program.getSourceFile(TYPES_FILE)!;
  const exported = tc.getExportsOfModule(tc.getSymbolAtLocation(source)!);
  const shared = exported.filter((s) => schemas[s.name] && !NOT_COMPARED[s.name]);

  it('compares a meaningful number of types (guards against a broken name match)', () => {
    expect(shared.length).toBeGreaterThan(100);
  });

  it('the frontend types match the backend contract, apart from the documented drift', () => {
    const checker = new Checker(schemas, tc);
    for (const sym of shared) {
      const type = tc.getDeclaredTypeOfSymbol(sym);
      const request = REQUEST_NAME.test(sym.name);
      const { parts } = (checker as any).split(type);
      if (parts.length === 1 && (checker as any).kind(parts[0]) === 'object') {
        checker.compareObject(sym.name, request, parts[0], (checker as any).unwrap(schemas[sym.name]).schema);
      } else {
        checker.compareType(sym.name, request, type, schemas[sym.name]);
      }
    }
    const found = [...new Set(checker.problems)].sort();
    const known = Object.keys(KNOWN_DRIFT).sort();
    const unexpected = found.filter((p) => !known.some((k) => p.startsWith(k)));
    const stale = known.filter((k) => !found.some((p) => p.startsWith(k)));
    expect({ unexpected, stale }).toEqual({ unexpected: [], stale: [] });
  });

  it('every endpoint the frontend calls exists in the OpenAPI paths', () => {
    const shape = (path: string) => path.replace(/\{[^}]*\}/g, '{}').replace(/\/+$/, '');
    const known = new Set(Object.keys(doc.paths).map(shape));
    const calls = new Set<string>();
    const srcRoot = resolve(__dirname, '..');
    const walk = (dir: string): string[] => readdirSync(dir, { withFileTypes: true }).flatMap((e) =>
      e.isDirectory() ? walk(resolve(dir, e.name)) : /\.(ts|tsx)$/.test(e.name) && !/\.test\./.test(e.name) && e.name !== 'types.ts'
        ? [resolve(dir, e.name)] : []);
    for (const file of walk(srcRoot)) {
      const text = readFileSync(file, 'utf8');
      // `${casePath(id)}` (client.ts) and `${base(id)}` (reportApi.ts) are the two path helpers.
      const expanded = text
        .replace(/\$\{casePath\([^)]*\)\}/g, '/api/v1/cases/{}')
        .replace(/\$\{base\([^)]*\)\}/g, '/api/v1/cases/{}/reports');
      for (const m of expanded.matchAll(/[`'"](\/api\/[^`'"?]*)/g)) {
        calls.add(shape(m[1].replace(/\$\{[^}]*\}/g, '{}')));
      }
    }
    expect(calls.size).toBeGreaterThan(15);
    expect([...calls].filter((c) => !known.has(c)).sort()).toEqual([]);
  });
});
