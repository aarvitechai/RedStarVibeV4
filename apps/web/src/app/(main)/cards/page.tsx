import type { Metadata } from "next";
import { TopBar } from "@/components/TopBar";
import { CardMaker } from "@/features/cards/CardMaker";
import styles from "@/features/ui.module.css";

export const metadata: Metadata = { title: "Make a card", robots: { index: false } };

export default function Page() {
  return (
    <main className={styles.shell}>
      <TopBar />
      <CardMaker />
    </main>
  );
}
