"use client";
/* eslint-disable @next/next/no-img-element -- story thumbnails are pre-sized renditions */

import { useRouter } from "next/navigation";
import { type FormEvent, useCallback, useEffect, useState } from "react";
import { Button } from "@/components/ui/Button";
import { ApiError, api } from "@/lib/api/client";
import type { Me } from "@/lib/api/types";
import { uploadFile } from "@/lib/upload";
import styles from "@/features/ui.module.css";
import { PostCard } from "./PostCard";
import type { Post, PostPage, StoryGroup } from "./types";

async function fetchPage(next: string | null): Promise<PostPage | "signed_out" | null> {
  try {
    return await api<PostPage>(`/api/v1/feed${next ? `?cursor=${encodeURIComponent(next)}` : ""}`);
  } catch (err) {
    return err instanceof ApiError && err.status === 401 ? "signed_out" : null;
  }
}

export function Feed() {
  const router = useRouter();
  const [me, setMe] = useState<Me | null>(null);
  const [items, setItems] = useState<Post[]>([]);
  const [cursor, setCursor] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [stories, setStories] = useState<StoryGroup[]>([]);
  const [viewing, setViewing] = useState<StoryGroup | null>(null);

  const apply = useCallback((next: string | null, result: PostPage | "signed_out" | null) => {
    if (result === "signed_out") return router.replace("/login?next=/feed");
    if (result) {
      setItems((cur) => (next ? [...cur, ...result.items] : result.items));
      setCursor(result.next_cursor ?? null);
    }
    setLoading(false);
  }, [router]);

  const load = useCallback((next: string | null) => fetchPage(next).then((r) => apply(next, r)), [apply]);

  useEffect(() => {
    void api<Me>("/api/v1/auth/me").then(setMe).catch(() => undefined);
    void api<StoryGroup[]>("/api/v1/stories/tray").then(setStories).catch(() => undefined);
    void load(null);
  }, [load]);

  async function viewStory(g: StoryGroup) {
    setViewing(g);
    for (const s of g.stories) void api(`/api/v1/stories/${s.id}/view`, { method: "POST" }).catch(() => undefined);
  }

  return (
    <>
      {stories.length ? (
        <section aria-label="Stories" className={styles.chips}>
          {stories.map((g) => (
            <button key={g.author_id} type="button" className={styles.chip} aria-pressed={!g.all_seen} onClick={() => void viewStory(g)}>
              {g.display_name}
            </button>
          ))}
        </section>
      ) : null}
      {viewing ? (
        <section className={styles.card} aria-label={`Stories by ${viewing.display_name}`}>
          <div className={styles.row}><strong>{viewing.display_name}</strong><Button size="sm" variant="ghost" onClick={() => setViewing(null)}>Close</Button></div>
          {viewing.stories.map((s) =>
            s.media.kind === "video"
              ? <video key={s.id} src={s.media.urls["video.mp4"]} autoPlay muted playsInline controls style={{ width: "100%" }} />
              : <img key={s.id} src={s.media.urls["1080.webp"] ?? s.media.urls["640.webp"]} alt="Story" style={{ width: "100%", height: "auto" }} />,
          )}
        </section>
      ) : null}
      <Composer onPosted={(p) => setItems((cur) => [p, ...cur])} onStory={() => void api<StoryGroup[]>("/api/v1/stories/tray").then(setStories)} />
      {items.length === 0 && !loading ? <p className={styles.empty}>Your feed is empty. Follow people and businesses to see their posts.</p> : null}
      {items.map((p) => (
        <PostCard key={p.id} post={p} meId={me?.id} onDeleted={() => setItems((cur) => cur.filter((x) => x.id !== p.id))} />
      ))}
      {loading ? <p className={styles.muted} aria-busy="true">Loading…</p> : null}
      {cursor && !loading ? <Button variant="secondary" onClick={() => { setLoading(true); void load(cursor); }}>Load more</Button> : null}
    </>
  );
}

function Composer({ onPosted, onStory }: { onPosted: (p: Post) => void; onStory: () => void }) {
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const form = e.currentTarget;
    const submitter = (e.nativeEvent as SubmitEvent).submitter as HTMLButtonElement | null;
    const asStory = submitter?.value === "story";
    const f = new FormData(form);
    const files = (f.getAll("files") as File[]).filter((x) => x.size > 0);
    setError(null);
    try {
      const ids: string[] = [];
      let kinds: string[] = [];
      for (const [i, file] of files.entries()) {
        setBusy(`Uploading ${i + 1} of ${files.length}…`);
        const kind = file.type.startsWith("video/") ? "video" : "image";
        kinds = [...kinds, kind];
        const isReel = f.get("reel") === "on" && kind === "video";
        ids.push((await uploadFile(file, kind, asStory ? "story" : isReel ? "reel" : "post")).id);
      }
      setBusy("Publishing…");
      if (asStory) {
        if (!ids[0]) throw new ApiError(400, { code: "no_media", message: "Choose a photo or video for your story.", details: {}, request_id: "-" });
        await api("/api/v1/stories", { method: "POST", body: JSON.stringify({ asset_id: ids[0] }) });
        onStory();
      } else {
        const reel = f.get("reel") === "on" && kinds.length === 1 && kinds[0] === "video";
        const post = await api<Post>("/api/v1/posts", {
          method: "POST",
          body: JSON.stringify({ caption: f.get("caption") || null, media_ids: ids, visibility: f.get("visibility"), kind: reel ? "reel" : "post" }),
        });
        onPosted(post);
      }
      form.reset();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not publish.");
    } finally {
      setBusy(null);
    }
  }

  return (
    <form className={styles.card} onSubmit={(e) => void submit(e)} aria-label="Create a post">
      <textarea name="caption" maxLength={2200} rows={3} placeholder="Share something with your city… #hashtags @mentions" className={styles.select} aria-label="Caption" />
      <input type="file" name="files" accept="image/jpeg,image/png,image/webp,video/mp4,video/quicktime,video/webm" multiple aria-label="Photos or videos" />
      <div className={styles.formRow}>
        <label className={styles.nav}><span>Who can see</span>
          <select name="visibility" className={styles.select} defaultValue="public">
            <option value="public">Everyone</option>
            <option value="followers">Followers</option>
          </select>
        </label>
        <label className={styles.nav}><input type="checkbox" name="reel" /> Post video as a reel</label>
      </div>
      {busy ? <p className={styles.muted} aria-busy="true">{busy}</p> : null}
      {error ? <p className={styles.alert} role="alert">{error}</p> : null}
      <div className={styles.nav}>
        <Button type="submit" name="mode" value="post" loading={busy !== null}>Post</Button>
        <Button type="submit" name="mode" value="story" variant="secondary" disabled={busy !== null}>Add to story</Button>
      </div>
    </form>
  );
}
