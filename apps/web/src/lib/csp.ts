/** Allowed media origin for user content (R2 CDN). */
const MEDIA_ORIGIN = process.env.NEXT_PUBLIC_MEDIA_ORIGIN ?? "";

export function buildCsp(nonce: string, isDev: boolean): string {
  const directives: Record<string, string[]> = {
    "default-src": ["'self'"],
    "script-src": ["'self'", `'nonce-${nonce}'`, "'strict-dynamic'", ...(isDev ? ["'unsafe-eval'"] : [])],
    "style-src": ["'self'", "'unsafe-inline'"],
    "img-src": ["'self'", "data:", "blob:", ...(MEDIA_ORIGIN ? [MEDIA_ORIGIN] : [])],
    "media-src": ["'self'", "blob:", ...(MEDIA_ORIGIN ? [MEDIA_ORIGIN] : [])],
    "worker-src": ["'self'", "blob:"],
    "font-src": ["'self'"],
    // CSP3 'self' covers same-origin ws:/wss: (our /ws); dev adds ws: for hot reload.
    "connect-src": ["'self'", ...(isDev ? ["ws:"] : [])],
    "frame-ancestors": ["'none'"],
    "base-uri": ["'self'"],
    "form-action": ["'self'"],
    "object-src": ["'none'"],
  };
  return Object.entries(directives)
    .map(([k, v]) => `${k} ${v.join(" ")}`)
    .join("; ");
}
