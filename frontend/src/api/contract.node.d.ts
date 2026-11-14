/**
 * Minimal Node typings for `contract.test.ts` only (ABB-29). The frontend does not depend on `@types/node`
 * and the contract test is the one place that reads files; declaring the three functions it uses avoids a new
 * dependency (AGENTS.md: dependencies need their own decision).
 */
declare module 'node:fs' {
  export function readFileSync(path: string, encoding: 'utf8'): string;
  export function readdirSync(path: string, options: { withFileTypes: true }): { name: string; isDirectory(): boolean }[];
}
declare module 'node:path' {
  export function resolve(...segments: string[]): string;
}
declare const process: { env: Record<string, string | undefined> };
declare const __dirname: string;
