import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { TopBar } from "@/components/TopBar";
import { ProfileActions } from "@/features/posts/ProfileActions";
import type { Profile } from "@/features/posts/types";
import styles from "@/features/ui.module.css";
import { serverGet } from "@/lib/api/server";

type Params = { params: Promise<{ username: string }> };
const SITE = process.env.RSV_PUBLIC_BASE_URL ?? "http://localhost:8080";
const HANDLE = /^[a-z0-9][a-z0-9_.]{1,28}[a-z0-9]$/i;

async function load(username: string) {
  return HANDLE.test(username) ? serverGet<Profile>(`/api/v1/profiles/${username.toLowerCase()}`) : null;
}

export async function generateMetadata({ params }: Params): Promise<Metadata> {
  const p = await load((await params).username);
  if (!p) return { title: "Profile not found" };
  return {
    title: `${p.display_name} (@${p.username})`,
    description: p.bio ?? `${p.display_name} on RedStarVibe`,
    openGraph: { title: p.display_name, description: p.bio ?? undefined, url: `${SITE}/${p.username}`, type: "profile" },
  };
}

export default async function ProfilePage({ params }: Params) {
  const p = await load((await params).username);
  if (!p) notFound();
  return (
    <main className={styles.shell}>
      <TopBar />
      <section className={styles.hero}>
        <h1 className={styles.h1}>{p.display_name}</h1>
        <p className={styles.muted}>@{p.username}{p.is_private ? " · private account" : ""}</p>
        {p.bio ? <p style={{ margin: 0 }}>{p.bio}</p> : null}
      </section>
      <ProfileActions username={p.username} />
    </main>
  );
}
