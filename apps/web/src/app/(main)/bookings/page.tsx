import type { Metadata } from "next";
import { TopBar } from "@/components/TopBar";
import { MyBookings } from "@/features/booking/MyBookings";
import styles from "@/features/ui.module.css";

export const metadata: Metadata = { title: "My bookings", robots: { index: false } };

export default function Page() {
  return (
    <main className={styles.shell}>
      <TopBar />
      <MyBookings />
    </main>
  );
}
