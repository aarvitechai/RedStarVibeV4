import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { TopBar } from "@/components/TopBar";
import { PostCard } from "@/features/posts/PostCard";
import type { Post } from "@/features/posts/types";
import styles from "@/features/ui.module.css";
import { serverGet } from "@/lib/api/server";

type Params = { params: Promise<{ id: string }> };
const SITE = process.env.RSV_PUBLIC_BASE_URL ?? "http://localhost:8080";

async function load(id: string) {
  return /^[0-9a-f-]{36}$/i.test(id) ? serverGet<Post>(`/api/v1/posts/${id}`) : null;
}

export async function generateMetadata({ params }: Params): Promise<Metadata> {
  const p = await load((await params).id);
  if (!p) return { title: "Post not found" };
  const image = p.media[0]?.urls["1080.webp"] ?? p.media[0]?.urls["poster.jpg"];
  return {
    title: `${p.author.display_name}: ${(p.caption ?? "Post").slice(0, 60)}`,
    description: p.caption ?? undefined,
    openGraph: { title: p.author.display_name, description: p.caption ?? undefined, url: `${SITE}/p/${p.id}`, images: image ? [{ url: image }] : [] },
  };
}

export default async function PostPage({ params }: Params) {
  const p = await load((await params).id);
  if (!p) notFound();
  return (
    <main className={styles.shell} style={{ maxWidth: 680 }}>
      <TopBar />
      <PostCard post={p} />
    </main>
  );
}
