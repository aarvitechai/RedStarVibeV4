import type { Metadata } from "next";
import { TopBar } from "@/components/TopBar";
import { Checkout } from "@/features/payments/Checkout";
import styles from "@/features/ui.module.css";

export const metadata: Metadata = { title: "Payment", robots: { index: false } };

export default async function PayPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return (
    <main className={styles.shell} style={{ maxWidth: 560 }}>
      <TopBar />
      <Checkout paymentId={id} />
    </main>
  );
}
