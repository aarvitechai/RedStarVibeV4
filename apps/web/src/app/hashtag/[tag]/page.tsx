import type { Metadata } from "next";
import { TopBar } from "@/components/TopBar";
import { PostCard } from "@/features/posts/PostCard";
import type { PostPage } from "@/features/posts/types";
import styles from "@/features/ui.module.css";
import { serverGet } from "@/lib/api/server";

type Params = { params: Promise<{ tag: string }> };

export async function generateMetadata({ params }: Params): Promise<Metadata> {
  return { title: `#${decodeURIComponent((await params).tag)}` };
}

export default async function HashtagPage({ params }: Params) {
  const tag = decodeURIComponent((await params).tag).slice(0, 60);
  const page = await serverGet<PostPage>(`/api/v1/hashtags/${encodeURIComponent(tag)}`);
  return (
    <main className={styles.shell} style={{ maxWidth: 680 }}>
      <TopBar />
      <h1 className={styles.h1}>#{tag}</h1>
      {!page || page.items.length === 0 ? <p className={styles.empty}>No public posts with #{tag} yet.</p> : null}
      {page?.items.map((p) => <PostCard key={p.id} post={p} />)}
    </main>
  );
}
