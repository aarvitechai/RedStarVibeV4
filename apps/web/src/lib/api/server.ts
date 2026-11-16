import "server-only";

/** Server-side fetch for SSR pages. Inside Docker the web container reaches the API directly (private network). */
const INTERNAL_API = process.env.RSV_INTERNAL_API_URL ?? "http://api:8000";

export async function serverGet<T>(path: string): Promise<T | null> {
  try {
    const r = await fetch(`${INTERNAL_API}${path}`, { cache: "no-store", signal: AbortSignal.timeout(5000) });
    if (r.status === 404) return null;
    if (!r.ok) throw new Error(`API ${r.status}`);
    return (await r.json()) as T;
  } catch (err) {
    if (err instanceof Error && err.message.startsWith("API 4")) return null;
    throw err;
  }
}
