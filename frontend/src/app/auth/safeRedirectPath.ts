/** Only same-origin absolute paths are accepted as post-login destinations (no open redirects). */
export function safeRedirectPath(value: unknown): string | null {
  if (typeof value !== 'string' || !value.startsWith('/') || value.startsWith('//')) return null;
  return value;
}
