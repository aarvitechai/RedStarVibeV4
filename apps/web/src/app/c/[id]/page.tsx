/* eslint-disable @next/next/no-img-element -- rendered card PNG */
import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import styles from "@/features/ui.module.css";
import { serverGet } from "@/lib/api/server";

type Params = { params: Promise<{ id: string }> };
interface Card { id: string; status: string; image_url: string | null; title: string }
const SITE = process.env.RSV_PUBLIC_BASE_URL ?? "http://localhost:8080";
const UUID = /^[0-9a-f-]{36}$/i;

async function load(id: string) {
  return UUID.test(id) ? serverGet<Card>(`/api/v1/cards/${id}`) : null;
}

export async function generateMetadata({ params }: Params): Promise<Metadata> {
  const card = await load((await params).id);
  if (!card) return { title: "Card not found" };
  return {
    title: card.title,
    openGraph: { title: card.title, description: "A card made with RedStarVibe", url: `${SITE}/c/${card.id}`, images: card.image_url ? [{ url: card.image_url }] : [] },
    twitter: { card: "summary_large_image", title: card.title },
  };
}

export default async function CardPage({ params }: Params) {
  const card = await load((await params).id);
  if (!card) notFound();
  return (
    <main className={styles.shell} style={{ maxWidth: 600 }}>
      <Link href="/" className={styles.brand}>RedStarVibe</Link>
      {card.image_url ? (
        <img src={card.image_url} alt={card.title} width={1080} height={1350} style={{ width: "100%", height: "auto", borderRadius: "var(--radius-card)" }} />
      ) : (
        <p className={styles.muted}>This card is still being created. Refresh in a moment.</p>
      )}
      <Link href="/cards" className={styles.navLink}>Make your own card — free</Link>
    </main>
  );
}
