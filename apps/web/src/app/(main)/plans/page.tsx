import type { Metadata } from "next";
import { TopBar } from "@/components/TopBar";
import { Plans } from "@/features/payments/Plans";
import styles from "@/features/ui.module.css";

export const metadata: Metadata = { title: "Plans" };

export default function Page() {
  return (
    <main className={styles.shell}>
      <TopBar />
      <Plans />
    </main>
  );
}
