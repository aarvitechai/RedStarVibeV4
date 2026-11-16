import type { Metadata } from "next";
import { TopBar } from "@/components/TopBar";
import { Feed } from "@/features/posts/Feed";
import styles from "@/features/ui.module.css";

export const metadata: Metadata = { title: "Feed", robots: { index: false } };

export default function Page() {
  return (
    <main className={styles.shell}>
      <TopBar />
      <Feed />
    </main>
  );
}
