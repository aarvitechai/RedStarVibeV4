import type { Metadata } from "next";
import { TopBar } from "@/components/TopBar";
import { AlbumsManager } from "@/features/albums/AlbumsManager";
import styles from "@/features/ui.module.css";

export const metadata: Metadata = { title: "Albums", robots: { index: false } };

export default function Page() {
  return (
    <main className={styles.shell}>
      <TopBar />
      <AlbumsManager />
    </main>
  );
}
