"use client";

import Link from "next/link";
import { type FormEvent, useState } from "react";
import { Picture } from "@/components/Picture";
import { Button } from "@/components/ui/Button";
import { ApiError, api } from "@/lib/api/client";
import { dateTimeIn } from "@/lib/format";
import styles from "@/features/ui.module.css";
import type { Comment, Post } from "./types";

function Caption({ text }: { text: string }) {
  // Hashtags and mentions become links; everything else stays plain text (React escapes it).
  const parts = text.split(/(#[\p{L}\p{N}_]{2,60}|@[a-z0-9][a-z0-9_.]{1,28}[a-z0-9])/giu);
  return (
    <p style={{ margin: 0, whiteSpace: "pre-line" }}>
      {parts.map((p, i) =>
        p.startsWith("#") ? <Link key={i} href={`/hashtag/${encodeURIComponent(p.slice(1).toLowerCase())}`}>{p}</Link>
        : p.startsWith("@") ? <Link key={i} href={`/${p.slice(1).toLowerCase()}`}>{p}</Link>
        : <span key={i}>{p}</span>,
      )}
    </p>
  );
}

export function PostCard({ post: initial, onDeleted, meId }: { post: Post; onDeleted?: () => void; meId?: string }) {
  const [post, setPost] = useState(initial);
  const [comments, setComments] = useState<Comment[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function toggleLike() {
    const on = !post.liked;
    setPost({ ...post, liked: on, like_count: post.like_count + (on ? 1 : -1) }); // optimistic, rolled back on error
    try {
      const r = await api<{ like_count: number }>(`/api/v1/posts/${post.id}/like`, { method: on ? "POST" : "DELETE" });
      setPost((p) => ({ ...p, like_count: r.like_count }));
    } catch (err) {
      setPost(post);
      setError(err instanceof ApiError ? err.message : "Could not update like.");
    }
  }

  async function toggleSave() {
    const on = !post.saved;
    setPost({ ...post, saved: on });
    try {
      await api(`/api/v1/posts/${post.id}/save`, { method: on ? "POST" : "DELETE" });
    } catch {
      setPost(post);
    }
  }

  async function openComments() {
    if (comments) return setComments(null);
    setComments(await api<Comment[]>(`/api/v1/posts/${post.id}/comments`).catch(() => []));
  }

  async function addComment(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const form = e.currentTarget;
    const body = String(new FormData(form).get("body") ?? "").trim();
    if (!body) return;
    const check = await api<{ warn: boolean; message: string | null }>("/api/v1/ai/comment-check", { method: "POST", body: JSON.stringify({ text: body }) }).catch(() => null);
    if (check?.warn && !confirm(`${check.message ?? "This might hurt someone."} Post anyway?`)) return;
    try {
      const c = await api<Comment>(`/api/v1/posts/${post.id}/comments`, { method: "POST", body: JSON.stringify({ body }) });
      setComments((cs) => [...(cs ?? []), c]);
      setPost((p) => ({ ...p, comment_count: p.comment_count + 1 }));
      form.reset();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not comment.");
    }
  }

  async function remove() {
    if (!confirm("Delete this post?")) return;
    await api(`/api/v1/posts/${post.id}`, { method: "DELETE" }).then(() => onDeleted?.()).catch(() => undefined);
  }

  async function report() {
    await api("/api/v1/reports", { method: "POST", body: JSON.stringify({ target_type: "post", target_id: post.id, reason: "spam" }) })
      .then(() => setError("Thanks — our team will review this post."))
      .catch(() => undefined);
  }

  return (
    <article className={styles.card} aria-label={`Post by ${post.author.display_name}`}>
      <div className={styles.row}>
        <Link href={`/${post.author.username}`}><strong>{post.author.display_name}</strong></Link>
        <Link href={`/p/${post.id}`} className={styles.muted}>{dateTimeIn(post.created_at, "Asia/Kolkata")}</Link>
      </div>
      {post.media.map((m) =>
        m.kind === "video" ? (
          <video key={m.id} src={m.urls["video.mp4"]} poster={m.urls["poster.jpg"]} controls playsInline preload="metadata"
            style={{ width: "100%", borderRadius: "var(--radius-control)" }} />
        ) : (
          <Picture key={m.id} urls={m.urls} alt={post.caption ?? "Photo"} width={m.width} height={m.height}
            className={styles.media} />
        ),
      )}
      {post.caption ? <Caption text={post.caption} /> : null}
      <div className={styles.nav}>
        <Button size="sm" variant={post.liked ? "primary" : "secondary"} onClick={() => void toggleLike()} aria-pressed={post.liked}>
          ♥ {post.like_count}
        </Button>
        <Button size="sm" variant="secondary" onClick={() => void openComments()} aria-expanded={comments !== null}>
          Comments {post.comment_count}
        </Button>
        <Button size="sm" variant={post.saved ? "primary" : "ghost"} onClick={() => void toggleSave()} aria-pressed={post.saved}>
          {post.saved ? "Saved" : "Save"}
        </Button>
        {meId === post.author.id ? <Button size="sm" variant="ghost" onClick={() => void remove()}>Delete</Button>
          : <Button size="sm" variant="ghost" onClick={() => void report()}>Report</Button>}
      </div>
      {error ? <p className={styles.muted} role="status">{error}</p> : null}
      {comments !== null ? (
        <div className={styles.form}>
          <ul className={styles.list}>
            {comments.map((c) => (
              <li key={c.id} style={{ paddingLeft: c.parent_id ? "var(--space-6)" : 0 }}>
                <Link href={`/${c.author.username}`}><strong>{c.author.display_name}</strong></Link> {c.body}
              </li>
            ))}
          </ul>
          <form className={styles.formRow} onSubmit={addComment}>
            <input name="body" maxLength={1000} placeholder="Add a comment…" className={styles.select} aria-label="Comment" />
            <Button type="submit" size="sm">Post</Button>
          </form>
        </div>
      ) : null}
    </article>
  );
}
