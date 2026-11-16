import type { Metadata } from "next";
import { TopBar } from "@/components/TopBar";
import { MyOrders } from "@/features/shop/MyOrders";
import styles from "@/features/ui.module.css";

export const metadata: Metadata = { title: "My orders", robots: { index: false } };

export default function Page() {
  return (
    <main className={styles.shell}>
      <TopBar />
      <MyOrders />
    </main>
  );
}
