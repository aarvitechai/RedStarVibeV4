import type { Metadata } from "next";
import Link from "next/link";
import { TopBar } from "@/components/TopBar";
import styles from "@/features/ui.module.css";
import { serverGet } from "@/lib/api/server";

export const metadata: Metadata = { title: "Help" };

interface Article { slug: string; title: string; body: string }

export default async function HelpPage() {
  const articles = (await serverGet<Article[]>("/api/v1/help")) ?? [];
  return (
    <main className={styles.shell}>
      <TopBar />
      <h1 className={styles.h1}>Help</h1>
      <p className={styles.muted}>Can&apos;t find it? <Link href="/assistant">Ask the assistant</Link>.</p>
      {articles.map((a) => (
        <section key={a.slug} id={a.slug} className={styles.card}>
          <h2 className={styles.h2}>{a.title}</h2>
          <p style={{ margin: 0 }}>{a.body}</p>
        </section>
      ))}
    </main>
  );
}
