import type { Metadata } from "next";
import { TopBar } from "@/components/TopBar";
import { Assistant } from "@/features/ai/Assistant";
import styles from "@/features/ui.module.css";

export const metadata: Metadata = { title: "Assistant" };

export default function Page() {
  return (
    <main className={styles.shell}>
      <TopBar />
      <Assistant />
    </main>
  );
}
