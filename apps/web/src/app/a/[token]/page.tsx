import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { Flipbook } from "@/features/albums/Flipbook";
import styles from "@/features/ui.module.css";
import { serverGet } from "@/lib/api/server";

type Params = { params: Promise<{ token: string }> };
interface Album { title: string; pages: { url: string; caption: string | null }[]; slideshow_url: string | null }

async function load(token: string) {
  return /^[A-Za-z0-9_-]{8,40}$/.test(token) ? serverGet<Album>(`/api/v1/albums/shared/${token}`) : null;
}

export async function generateMetadata({ params }: Params): Promise<Metadata> {
  const a = await load((await params).token);
  if (!a) return { title: "Album not found" };
  return { title: a.title, robots: { index: false }, openGraph: { title: a.title, images: a.pages[0] ? [{ url: a.pages[0].url }] : [] } };
}

export default async function AlbumPage({ params }: Params) {
  const a = await load((await params).token);
  if (!a) notFound();
  return (
    <main className={styles.shell} style={{ maxWidth: 720 }}>
      <Link href="/" className={styles.brand}>RedStarVibe</Link>
      <h1 className={styles.h1}>{a.title}</h1>
      <Flipbook title={a.title} pages={a.pages} />
      {a.slideshow_url ? <video src={a.slideshow_url} controls playsInline style={{ width: "100%", borderRadius: "var(--radius-card)" }} /> : null}
    </main>
  );
}
