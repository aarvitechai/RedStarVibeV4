"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { Button } from "@/components/ui/Button";
import { ApiError, api } from "@/lib/api/client";
import styles from "@/features/ui.module.css";
import { PostCard } from "./PostCard";
import type { Post, PostPage, Profile } from "./types";

/** Client part of the profile page: relationship-aware actions and the posts list (needs the viewer's cookie). */
export function ProfileActions({ username }: { username: string }) {
  const router = useRouter();
  const [profile, setProfile] = useState<Profile | null>(null);
  const [posts, setPosts] = useState<Post[] | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const [tick, setTick] = useState(0);

  useEffect(() => {
    const c = new AbortController();
    api<Profile>(`/api/v1/profiles/${username}`, { signal: c.signal }).then(setProfile).catch(() => undefined);
    api<PostPage>(`/api/v1/profiles/${username}/posts`, { signal: c.signal }).then((p) => setPosts(p.items)).catch(() => setPosts([]));
    return () => c.abort();
  }, [username, tick]);

  async function act(path: string, method: "POST" | "DELETE", note?: string) {
    try {
      await api(`/api/v1/profiles/${username}/${path}`, { method });
      if (note) setMsg(note);
      setTick((t) => t + 1);
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) router.push(`/login?next=/${username}`);
      else setMsg(err instanceof ApiError ? err.message : "Action failed.");
    }
  }

  async function message() {
    try {
      const conv = await api<{ id: string }>(`/api/v1/chat/direct/${username}`, { method: "POST" });
      router.push(`/messages?c=${conv.id}`);
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) router.push(`/login?next=/${username}`);
    }
  }

  if (!profile) return null;
  const self = profile.relationship === "self";
  return (
    <>
      <div className={styles.nav}>
        {self ? <Button variant="secondary" onClick={() => router.push("/account")}>Edit profile</Button> : (
          <>
            {profile.relationship === "following" ? <Button variant="secondary" onClick={() => void act("follow", "DELETE")}>Following</Button>
              : profile.relationship === "requested" ? <Button variant="secondary" onClick={() => void act("follow", "DELETE")}>Requested</Button>
              : <Button onClick={() => void act("follow", "POST")}>Follow</Button>}
            <Button variant="secondary" onClick={() => void message()}>Message</Button>
            <Button variant="ghost" onClick={() => void act("mute", "POST", "Muted. You won't see their posts in your feed.")}>Mute</Button>
            <Button variant="ghost" onClick={() => { if (confirm(`Block @${username}?`)) void act("block", "POST", "Blocked."); }}>Block</Button>
          </>
        )}
      </div>
      <p className={styles.muted}>{profile.followers} followers · {profile.following} following</p>
      {msg ? <p className={styles.muted} role="status">{msg}</p> : null}
      {!profile.can_view_content ? <p className={styles.empty}>This account is private. Follow to see their posts.</p> : null}
      {posts?.length === 0 && profile.can_view_content ? <p className={styles.empty}>No posts yet.</p> : null}
      {posts?.map((p) => <PostCard key={p.id} post={p} meId={self ? profile.id : undefined} />)}
    </>
  );
}
