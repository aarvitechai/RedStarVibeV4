"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api/client";
import styles from "@/features/ui.module.css";
import { PostCard } from "./PostCard";
import type { Post, PostPage } from "./types";

export function Reels() {
  const [items, setItems] = useState<Post[] | null>(null);
  useEffect(() => {
    const c = new AbortController();
    api<PostPage>("/api/v1/reels", { signal: c.signal }).then((p) => setItems(p.items)).catch(() => setItems([]));
    return () => c.abort();
  }, []);
  if (items === null) return <p className={styles.muted} aria-busy="true">Loading reels…</p>;
  if (items.length === 0) return <p className={styles.empty}>No reels yet. Post a short video and tick “Post video as a reel”.</p>;
  return <>{items.map((p) => <PostCard key={p.id} post={p} />)}</>;
}
