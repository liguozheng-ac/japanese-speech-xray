type Schema = {
  type?: string;
  const?: unknown;
  enum?: unknown[];
  $ref?: string;
  anyOf?: Schema[];
  properties?: Record<string, Schema>;
  required?: string[];
  additionalProperties?: boolean;
  items?: Schema;
  minimum?: number;
  maximum?: number;
  minItems?: number;
  maxItems?: number;
};
// This validates the frozen serialization schema, not acoustic or scientific judgments.
export function validateContract(
  value: unknown,
  schema: Schema,
  definitions: Record<string, Schema>,
  path = "$",
): void {
  const fail = (): never => {
    throw new Error(`后端响应不符合 API v1 合约：${path}`);
  };
  if (schema.$ref) {
    validateContract(
      value,
      definitions[schema.$ref.split("/").at(-1)!],
      definitions,
      path,
    );
    return;
  }
  if (schema.anyOf) {
    for (const branch of schema.anyOf) {
      try {
        validateContract(value, branch, definitions, path);
        return;
      } catch {
        /* Try next union branch. */
      }
    }
    fail();
  }
  if (schema.const !== undefined && value !== schema.const) fail();
  if (schema.enum && !schema.enum.includes(value)) fail();
  switch (schema.type) {
    case "null":
      if (value !== null) fail();
      break;
    case "boolean":
      if (typeof value !== "boolean") fail();
      break;
    case "string":
      if (typeof value !== "string") fail();
      break;
    case "integer":
    case "number":
      if (
        typeof value !== "number" ||
        !Number.isFinite(value) ||
        (schema.type === "integer" && !Number.isInteger(value)) ||
        (schema.minimum !== undefined && value < schema.minimum) ||
        (schema.maximum !== undefined && value > schema.maximum)
      )
        fail();
      break;
    case "array":
      if (!Array.isArray(value)) fail();
      if (
        schema.minItems !== undefined &&
        (value as unknown[]).length < schema.minItems
      )
        fail();
      if (
        schema.maxItems !== undefined &&
        (value as unknown[]).length > schema.maxItems
      )
        fail();
      (value as unknown[]).forEach((v, i) =>
        validateContract(v, schema.items!, definitions, `${path}[${i}]`),
      );
      break;
    case "object":
      if (!value || typeof value !== "object" || Array.isArray(value)) fail();
      {
        const obj = value as Record<string, unknown>;
        for (const key of schema.required ?? []) if (!(key in obj)) fail();
        for (const [key, v] of Object.entries(obj)) {
          const child = schema.properties?.[key];
          if (child) validateContract(v, child, definitions, `${path}.${key}`);
          else if (schema.additionalProperties === false) fail();
        }
      }
      break;
  }
}
