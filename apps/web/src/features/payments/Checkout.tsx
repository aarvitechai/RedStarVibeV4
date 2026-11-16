"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { Button } from "@/components/ui/Button";
import { ApiError, api } from "@/lib/api/client";
import { rupees } from "@/lib/format";
import styles from "@/features/ui.module.css";

interface Intent { payment_id: string; amount_paise: number; provider: string; provider_order_id: string; public_key: string; status: string }
interface RazorpayCtor { new (opts: Record<string, unknown>): { open(): void } }

function loadRazorpay(): Promise<RazorpayCtor> {
  const w = window as unknown as { Razorpay?: RazorpayCtor };
  if (w.Razorpay) return Promise.resolve(w.Razorpay);
  return new Promise((resolve, reject) => {
    const s = document.createElement("script"); // allowed by CSP 'strict-dynamic' (inserted by our nonced bundle)
    s.src = "https://checkout.razorpay.com/v1/checkout.js";
    s.onload = () => (w.Razorpay ? resolve(w.Razorpay) : reject(new Error("Razorpay not available")));
    s.onerror = () => reject(new Error("Could not load Razorpay"));
    document.head.appendChild(s);
  });
}

/** The browser result is only a hint: we always wait for the server (webhook or reconciliation) to say "paid". */
export function Checkout({ paymentId }: { paymentId: string }) {
  const [intent, setIntent] = useState<Intent | null>(null);
  const [state, setState] = useState<"ready" | "waiting" | "paid" | "error">("ready");
  const [msg, setMsg] = useState<string | null>(null);

  const refresh = useCallback(() => api<Intent>(`/api/v1/payments/${paymentId}`).then((i) => {
    setIntent(i);
    if (i.status === "paid") setState("paid");
    return i;
  }), [paymentId]);

  useEffect(() => { void refresh().catch((err: unknown) => { setState("error"); setMsg(err instanceof ApiError ? err.message : "Payment not found."); }); }, [refresh]);

  useEffect(() => {
    if (state !== "waiting") return;
    const t = setInterval(() => void refresh(), 2000);
    return () => clearInterval(t);
  }, [state, refresh]);

  async function pay() {
    if (!intent) return;
    if (intent.provider === "sandbox") {
      setState("waiting");
      await api(`/api/v1/payments/${intent.payment_id}/sandbox-complete`, { method: "POST" }).catch(() => undefined);
      await refresh();
      return;
    }
    try {
      const Razorpay = await loadRazorpay();
      new Razorpay({
        key: intent.public_key, order_id: intent.provider_order_id, amount: intent.amount_paise, currency: "INR", name: "RedStarVibe",
        handler: () => setState("waiting"), modal: { ondismiss: () => setState("ready") }, theme: { color: "#C8102E" },
      }).open();
    } catch (err) {
      setMsg(err instanceof Error ? err.message : "Could not open checkout.");
    }
  }

  if (state === "error") return <p className={styles.alert} role="alert">{msg}</p>;
  if (!intent) return <p className={styles.muted} aria-busy="true">Loading…</p>;
  return (
    <section className={styles.card} aria-labelledby="pay-title">
      <h1 id="pay-title" className={styles.h2}>Pay {rupees(intent.amount_paise)}</h1>
      {intent.provider === "sandbox" ? <p className={styles.muted}>Test mode: no real money moves. Real Razorpay checkout opens once keys are configured.</p> : null}
      {state === "paid" ? (
        <>
          <p className={styles.success} role="status">Payment received. Thank you!</p>
          <Link href="/orders">Back to my orders</Link>
        </>
      ) : state === "waiting" ? (
        <p className={styles.muted} aria-busy="true">Confirming with the bank…</p>
      ) : (
        <Button onClick={() => void pay()}>Pay securely (UPI / cards)</Button>
      )}
      {msg ? <p className={styles.alert} role="alert">{msg}</p> : null}
    </section>
  );
}
