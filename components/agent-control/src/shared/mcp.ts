export type TextResult = ReturnType<typeof asText>;

export function asText(data: unknown) {
  return {
    content: [{ type: 'text' as const, text: JSON.stringify(data, null, 2) }],
  };
}
