"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { Button } from "@/components/ui/Button";
import { ApiError, api } from "@/lib/api/client";
import { rupees } from "@/lib/format";
import styles from "@/features/ui.module.css";

interface Plan { code: string; name: string; price_paise: number; ai_calls_per_day: number; features: string[] }
interface Ent { plan: string; renews_at: string | null }

export function Plans() {
  const router = useRouter();
  const [plans, setPlans] = useState<Plan[]>([]);
  const [ent, setEnt] = useState<Ent | null>(null);
  const [msg, setMsg] = useState<string | null>(null);

  useEffect(() => {
    void api<Plan[]>("/api/v1/plans").then(setPlans).catch(() => undefined);
    void api<Ent>("/api/v1/me/entitlements").then(setEnt).catch(() => undefined);
  }, []);

  async function choose(code: string) {
    try {
      const i = await api<{ checkout_url: string }>("/api/v1/payments/intents", { method: "POST",
        headers: { "Idempotency-Key": `plan-${code}-${new Date().toISOString().slice(0, 7)}` },
        body: JSON.stringify({ purpose: "subscription", reference_id: code }) });
      router.push(i.checkout_url);
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) router.push("/login?next=/plans");
      else setMsg(err instanceof ApiError ? err.message : "Could not start payment.");
    }
  }

  return (
    <section className={styles.card} aria-labelledby="plans-title">
      <h1 id="plans-title" className={styles.h2}>Plans</h1>
      {ent ? <p className={styles.muted}>Your plan: <strong>{ent.plan}</strong>{ent.renews_at ? ` · renews ${new Date(ent.renews_at).toLocaleDateString()}` : ""}</p> : null}
      {msg ? <p className={styles.alert} role="alert">{msg}</p> : null}
      <ul className={styles.list}>
        {plans.map((p) => (
          <li key={p.code} className={styles.card}>
            <div className={styles.row}><strong>{p.name}</strong><span className={styles.price}>{p.price_paise ? `${rupees(p.price_paise)} / month` : "Free"}</span></div>
            <span className={styles.muted}>{p.features.join(" · ")} · {p.ai_calls_per_day} AI suggestions a day</span>
            {p.price_paise > 0 && ent?.plan !== p.code ? <Button size="sm" onClick={() => void choose(p.code)}>Choose {p.name}</Button> : null}
          </li>
        ))}
      </ul>
    </section>
  );
}
