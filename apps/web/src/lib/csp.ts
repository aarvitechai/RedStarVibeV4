/** Allowed media origin for user content (R2 CDN). */
const MEDIA_ORIGIN = process.env.NEXT_PUBLIC_MEDIA_ORIGIN ?? "";
/** LiveKit signalling server, e.g. ws://localhost:7880 locally or wss://<project>.livekit.cloud. */
const LIVEKIT_ORIGIN = process.env.NEXT_PUBLIC_LIVEKIT_ORIGIN ?? "";

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
    "connect-src": ["'self'", "https://api.razorpay.com", "https://lumberjack.razorpay.com", ...(LIVEKIT_ORIGIN ? [LIVEKIT_ORIGIN, LIVEKIT_ORIGIN.replace(/^ws/, "http")] : []), ...(isDev ? ["ws:"] : [])],
    // Razorpay Checkout (Phase 6) and LiveKit (Phase 7) are the only third-party origins.
    "frame-src": ["https://api.razorpay.com", "https://checkout.razorpay.com"],
    "frame-ancestors": ["'none'"],
    "base-uri": ["'self'"],
    "form-action": ["'self'"],
    "object-src": ["'none'"],
  };
  return Object.entries(directives)
    .map(([k, v]) => `${k} ${v.join(" ")}`)
    .join("; ");
}
