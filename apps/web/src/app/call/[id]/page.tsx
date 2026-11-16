import type { Metadata } from "next";
import { TopBar } from "@/components/TopBar";
import { CallRoom } from "@/features/calls/CallRoom";
import styles from "@/features/ui.module.css";

export const metadata: Metadata = { title: "Call", robots: { index: false } };

type Props = { params: Promise<{ id: string }>; searchParams: Promise<{ answer?: string }> };

export default async function CallPage({ params, searchParams }: Props) {
  const { id } = await params;
  const { answer } = await searchParams;
  return (
    <main className={styles.shell} style={{ maxWidth: 720 }}>
      <TopBar />
      <CallRoom conversationId={id} answering={answer === "1"} />
    </main>
  );
}
