"use client";

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { Button } from "@/components/ui/Button";
import { ApiError, api } from "@/lib/api/client";
import { dateTimeIn, rupees } from "@/lib/format";
import styles from "@/features/ui.module.css";
import type { components } from "../../../../../packages/api-types";

type Order = components["schemas"]["OrderOut"];
type EventBooking = components["schemas"]["EventBookingOut"];

export function MyOrders() {
  const router = useRouter();
  const [orders, setOrders] = useState<Order[] | null>(null);
  const [events, setEvents] = useState<EventBooking[]>([]);
  const [msg, setMsg] = useState<string | null>(null);

  const load = useCallback(() => {
    api<Order[]>("/api/v1/orders/mine").then(setOrders).catch((err: unknown) => {
      if (err instanceof ApiError && err.status === 401) router.replace("/login?next=/orders");
    });
    api<EventBooking[]>("/api/v1/event-bookings/mine").then(setEvents).catch(() => undefined);
  }, [router]);
  useEffect(() => { load(); }, [load]);

  async function pay(kind: "order" | "event_booking", id: string) {
    try {
      const intent = await api<{ checkout_url: string }>("/api/v1/payments/intents", { method: "POST",
        headers: { "Idempotency-Key": `${kind}-${id}` }, body: JSON.stringify({ purpose: kind, reference_id: id }) });
      window.location.assign(intent.checkout_url);
    } catch (err) {
      setMsg(err instanceof ApiError ? err.message : "Payment could not start.");
    }
  }

  return (
    <section className={styles.card} aria-labelledby="orders-title">
      <h1 id="orders-title" className={styles.h2}>My orders</h1>
      {msg ? <p className={styles.alert} role="alert">{msg}</p> : null}
      {orders?.length === 0 && events.length === 0 ? <p className={styles.empty}>No orders yet.</p> : null}
      <ul className={styles.list}>
        {orders?.map((o) => (
          <li key={o.id} className={styles.card}>
            <div className={styles.row}><span>{o.items.map((i) => `${i.qty}× ${i.name}`).join(", ")}</span><span className={styles.badge}>{o.status}</span></div>
            <span className={styles.muted}>{rupees(o.total_paise)} · {dateTimeIn(o.created_at, "Asia/Kolkata")} · {o.payment_status}</span>
            <div className={styles.nav}>
              {o.status === "placed" ? <Button size="sm" variant="ghost" onClick={() => void api(`/api/v1/orders/${o.id}/status`, { method: "POST", body: JSON.stringify({ status: "cancelled" }) }).then(load)}>Cancel</Button> : null}
              {o.payment_status !== "paid" && o.status !== "cancelled" ? <Button size="sm" onClick={() => void pay("order", o.id)}>Pay {rupees(o.total_paise)}</Button> : null}
            </div>
          </li>
        ))}
        {events.map((e) => (
          <li key={e.id} className={styles.card}>
            <div className={styles.row}><span>{e.package_name} · {e.event_date}</span><span className={styles.badge} data-status={e.status}>{e.status}</span></div>
            <span className={styles.muted}>{rupees(e.price_paise)} · {e.guests} guests · {e.payment_status}</span>
            {e.payment_status !== "paid" && (e.status === "pending" || e.status === "confirmed")
              ? <Button size="sm" onClick={() => void pay("event_booking", e.id)}>Pay advance to lock the date</Button> : null}
          </li>
        ))}
      </ul>
    </section>
  );
}
