import { ApiError, api } from "@/lib/api/client";

export interface Asset {
  id: string;
  kind: string;
  status: "pending" | "processing" | "ready" | "failed";
  urls: Record<string, string>;
  width: number | null;
  height: number | null;
  duration_s: number | null;
  error: string | null;
}

type Kind = "image" | "video" | "audio";

/** Presigned direct upload (Blueprint 9.1): the file never passes through our API servers. */
export async function uploadFile(file: File, kind: Kind, purpose: string, signal?: AbortSignal): Promise<Asset> {
  const intent = await api<{ asset_id: string; upload_url: string; headers: Record<string, string> }>("/api/v1/media/uploads", {
    method: "POST",
    body: JSON.stringify({ kind, purpose, content_type: file.type, size_bytes: file.size }),
    signal,
  });
  const put = await fetch(intent.upload_url, { method: "PUT", headers: intent.headers, body: file, signal });
  if (!put.ok) throw new ApiError(put.status, { code: "upload_failed", message: "Upload failed. Please try again.", details: {}, request_id: "-" });
  await api(`/api/v1/media/uploads/${intent.asset_id}/complete`, { method: "POST", signal });
  return waitForAsset(intent.asset_id, signal);
}

export async function waitForAsset(id: string, signal?: AbortSignal, timeoutMs = 120_000): Promise<Asset> {
  const started = Date.now();
  let delay = 500;
  for (;;) {
    const a = await api<Asset>(`/api/v1/media/${id}`, { signal });
    if (a.status === "ready") return a;
    if (a.status === "failed") throw new ApiError(422, { code: "media_failed", message: a.error ?? "This file could not be processed.", details: {}, request_id: "-" });
    if (Date.now() - started > timeoutMs) throw new ApiError(504, { code: "media_timeout", message: "Processing is taking longer than usual.", details: {}, request_id: "-" });
    await new Promise((r) => setTimeout(r, delay));
    delay = Math.min(delay * 1.5, 3000);
  }
}

export function bestImage(urls: Record<string, string>, width: 320 | 640 | 1080 = 640): string | undefined {
  return urls[`${width}.webp`] ?? urls["640.webp"] ?? urls["320.webp"] ?? Object.values(urls)[0];
}
