"use client";

import { useRouter } from "next/navigation";
import { type FormEvent, useCallback, useEffect, useState } from "react";
import { Button } from "@/components/ui/Button";
import { ApiError, api } from "@/lib/api/client";
import type { Booking, BookingPage } from "@/lib/api/types";
import { dateTimeIn, rupees } from "@/lib/format";
import styles from "@/features/ui.module.css";

const TZ = "Asia/Kolkata";

export function MyBookings() {
  const router = useRouter();
  const [items, setItems] = useState<Booking[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(
    (signal?: AbortSignal) =>
      api<BookingPage>("/api/v1/bookings/mine", { signal })
        .then((p) => setItems(p.items))
        .catch((err: unknown) => {
          if (signal?.aborted) return;
          if (err instanceof ApiError && err.status === 401) router.replace("/login?next=/bookings");
          else setError(err instanceof ApiError ? err.message : "Could not load bookings.");
        }),
    [router],
  );

  useEffect(() => {
    const c = new AbortController();
    void load(c.signal);
    return () => c.abort();
  }, [load]);

  async function cancel(id: string) {
    try {
      await api(`/api/v1/bookings/${id}/cancel`, { method: "POST" });
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not cancel.");
    }
  }

  return (
    <section className={styles.card} aria-labelledby="mine-title">
      <h1 id="mine-title" className={styles.h2}>My bookings</h1>
      {error ? <p className={styles.alert} role="alert">{error}</p> : null}
      {items === null && !error ? <p className={styles.muted} aria-busy="true">Loading…</p> : null}
      {items?.length === 0 ? <p className={styles.empty}>No bookings yet. Find a local business and book a time.</p> : null}
      <ul className={styles.list}>
        {items?.map((b) => (
          <li key={b.id} className={styles.card}>
            <div className={styles.row}>
              <span><strong>{b.service_name}</strong> · {dateTimeIn(b.starts_at, TZ)}</span>
              <span className={styles.badge} data-status={b.status}>{b.status}</span>
            </div>
            <span className={styles.price}>{rupees(b.price_paise)}</span>
            {(b.status === "pending" || b.status === "confirmed") && new Date(b.starts_at) > new Date() ? (
              <Button size="sm" variant="ghost" onClick={() => void cancel(b.id)}>Cancel booking</Button>
            ) : null}
            {b.status === "done" ? <ReviewForm bookingId={b.id} /> : null}
          </li>
        ))}
      </ul>
    </section>
  );
}

function ReviewForm({ bookingId }: { bookingId: string }) {
  const [rating, setRating] = useState(5);
  const [state, setState] = useState<{ ok: boolean; text: string } | null>(null);

  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const body = new FormData(e.currentTarget).get("body");
    try {
      await api(`/api/v1/bookings/${bookingId}/review`, { method: "POST", body: JSON.stringify({ rating, body: body || null }) });
      setState({ ok: true, text: "Thanks for your review!" });
    } catch (err) {
      setState({ ok: false, text: err instanceof ApiError ? err.message : "Could not save the review." });
    }
  }

  if (state?.ok) return <p className={styles.success}>{state.text}</p>;
  return (
    <form className={styles.form} onSubmit={submit}>
      <div className={styles.chips} role="group" aria-label="Rating">
        {[1, 2, 3, 4, 5].map((n) => (
          <button key={n} type="button" className={styles.chip} aria-pressed={n === rating} onClick={() => setRating(n)}>
            {n} ★
          </button>
        ))}
      </div>
      <label className={styles.form}>
        <span>Your review (optional)</span>
        <textarea name="body" maxLength={1000} rows={3} className={styles.select} />
      </label>
      {state ? <p className={styles.alert} role="alert">{state.text}</p> : null}
      <Button type="submit" size="sm">Post review</Button>
    </form>
  );
}
