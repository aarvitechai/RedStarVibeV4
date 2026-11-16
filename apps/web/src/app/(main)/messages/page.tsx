import type { Metadata } from "next";
import { Suspense } from "react";
import { TopBar } from "@/components/TopBar";
import { Messages } from "@/features/chat/Messages";
import styles from "@/features/ui.module.css";

export const metadata: Metadata = { title: "Messages", robots: { index: false } };

export default function Page() {
  return (
    <main className={styles.shell}>
      <TopBar />
      <Suspense>
        <Messages />
      </Suspense>
    </main>
  );
}
