import type { Metadata } from "next";
import { TopBar } from "@/components/TopBar";
import { Dashboard } from "@/features/business/Dashboard";
import styles from "@/features/ui.module.css";

export const metadata: Metadata = { title: "My business", robots: { index: false } };

export default function Page() {
  return (
    <main className={styles.shell}>
      <TopBar />
      <Dashboard />
    </main>
  );
}
