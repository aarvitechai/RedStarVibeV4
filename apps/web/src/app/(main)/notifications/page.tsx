import type { Metadata } from "next";
import { TopBar } from "@/components/TopBar";
import { NotificationsList } from "@/features/notifications/NotificationsList";
import styles from "@/features/ui.module.css";

export const metadata: Metadata = { title: "Notifications", robots: { index: false } };

export default function Page() {
  return (
    <main className={styles.shell}>
      <TopBar />
      <NotificationsList />
    </main>
  );
}
