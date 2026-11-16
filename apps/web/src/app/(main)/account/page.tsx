import type { Metadata } from "next";
import { AccountPanel } from "@/features/auth/AccountPanel";
import styles from "@/features/auth/auth.module.css";

export const metadata: Metadata = { title: "Account", robots: { index: false } };

export default function AccountPage() {
  return (
    <main className={styles.page}>
      <AccountPanel />
    </main>
  );
}
