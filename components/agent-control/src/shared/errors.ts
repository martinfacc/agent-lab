export type ErrorDetails = {
  code: string | number | null;
  stdout: string | null;
  stderr: string | null;
  message: string;
};

function property(value: unknown, name: string): unknown {
  if (typeof value !== 'object' || value === null || !(name in value)) {
    return undefined;
  }
  return value[name as keyof typeof value];
}

function text(value: unknown): string | null {
  return typeof value === 'string' && value.trim() ? value.trim() : null;
}

export function errorDetails(error: unknown): ErrorDetails {
  const code = property(error, 'code');
  const message = error instanceof Error ? error.message : String(error);

  return {
    code: typeof code === 'string' || typeof code === 'number' ? code : null,
    stdout: text(property(error, 'stdout')),
    stderr: text(property(error, 'stderr')),
    message,
  };
}

export function hasErrorCode(error: unknown, code: string): boolean {
  return property(error, 'code') === code;
}
