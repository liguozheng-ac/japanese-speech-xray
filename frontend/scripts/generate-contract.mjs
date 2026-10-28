import fs from "node:fs";
import ts from "typescript";
const schema = JSON.parse(
  fs.readFileSync(
    new URL(
      "../../data/contracts/api-v1-analysis.schema.json",
      import.meta.url,
    ),
  ),
);
function type(s) {
  if (s.$ref) return s.$ref.split("/").at(-1);
  if (s.const !== undefined) return JSON.stringify(s.const);
  if (s.enum) return s.enum.map(JSON.stringify).join(" | ");
  if (s.anyOf) return s.anyOf.map(type).join(" | ");
  if (s.type === "array") return `Array<${type(s.items)}>`;
  if (s.type === "object")
    return `{ ${Object.entries(s.properties ?? {})
      .map(([k, v]) => `${k}${s.required?.includes(k) ? "" : "?"}: ${type(v)}`)
      .join("; ")} }`;
  return (
    {
      integer: "number",
      number: "number",
      string: "string",
      boolean: "boolean",
      null: "null",
    }[s.type] ?? "unknown"
  );
}
fs.mkdirSync(new URL("../src/api/", import.meta.url), { recursive: true });
const generated =
    "// Generated from the frozen API v1 serialization schema; run node scripts/generate-contract.mjs.\n" +
    Object.entries({ ...schema.$defs, SpeechXRayAnalysisResponse: schema })
      .map(([k, v]) => `export type ${k} = ${type(v)};`)
      .join("\n") +
    "\n";
fs.writeFileSync(
  new URL("../src/api/contract.ts", import.meta.url),
  ts.createPrinter().printFile(ts.createSourceFile('contract.ts',generated,ts.ScriptTarget.ES2022,true)),
);
