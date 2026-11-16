import type { Metadata } from "next";
import { TopBar } from "@/components/TopBar";
import { Reels } from "@/features/posts/Reels";
import styles from "@/features/ui.module.css";

export const metadata: Metadata = { title: "Reels", robots: { index: false } };

export default function Page() {
  return (
    <main className={styles.shell}>
      <TopBar />
      <Reels />
    </main>
  );
}
