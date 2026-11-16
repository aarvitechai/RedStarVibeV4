"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { Button } from "@/components/ui/Button";
import { ApiError, api } from "@/lib/api/client";
import type { Booking, Service, SlotsResponse } from "@/lib/api/types";
import { dayLabel, isoDateIn, rupees, timeIn } from "@/lib/format";
import styles from "@/features/ui.module.css";

interface Props {
  businessId: string;
  slug: string;
  timezone: string;
  services: Service[];
}

type SlotState = { kind: "loading" } | { kind: "ready"; data: SlotsResponse } | { kind: "error"; message: string };

export function BookingWidget({ businessId, slug, timezone, services }: Props) {
  const router = useRouter();
  const days = Array.from({ length: 7 }, (_, i) => isoDateIn(timezone, i));
  const [serviceId, setServiceId] = useState(services[0]?.id ?? "");
  const [day, setDay] = useState(days[0] ?? "");
  const [slots, setSlots] = useState<SlotState>({ kind: "loading" });
  const [picked, setPicked] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState<Booking | null>(null);
  // One key per booking attempt: retries of the same attempt reuse it, so a flaky network never double-books.
  const attemptKey = useRef<string>("");

  useEffect(() => {
    if (!serviceId || !day) return;
    const controller = new AbortController();
    const q = new URLSearchParams({ service_id: serviceId, date: day });
    api<SlotsResponse>(`/api/v1/businesses/${businessId}/slots?${q}`, { signal: controller.signal })
      .then((data) => setSlots({ kind: "ready", data }))
      .catch((err: unknown) => {
        if (!controller.signal.aborted) setSlots({ kind: "error", message: err instanceof ApiError ? err.message : "Could not load times." });
      });
    return () => controller.abort();
  }, [businessId, serviceId, day]);

  function choose(next: { serviceId?: string; day?: string }) {
    if (next.serviceId) setServiceId(next.serviceId);
    if (next.day) setDay(next.day);
    setSlots({ kind: "loading" });
    setPicked(null);
    setError(null);
  }

  function pick(startsAt: string) {
    setPicked(startsAt);
    attemptKey.current = crypto.randomUUID();
    setError(null);
  }

  async function confirm() {
    if (!picked) return;
    setBusy(true);
    setError(null);
    try {
      const booking = await api<Booking>("/api/v1/bookings", {
        method: "POST",
        headers: { "Idempotency-Key": attemptKey.current },
        body: JSON.stringify({ business_id: businessId, service_id: serviceId, starts_at: picked }),
      });
      setDone(booking);
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        router.push(`/login?next=/business/${slug}`);
        return;
      }
      setError(err instanceof ApiError ? err.message : "Could not book. Please try again.");
      if (err instanceof ApiError && err.body.code === "slot_taken") choose({ day });
    } finally {
      setBusy(false);
    }
  }

  if (services.length === 0) return <p className={styles.empty}>This business has not added bookable services yet.</p>;

  if (done)
    return (
      <div className={styles.card} role="status">
        <p className={styles.success}>
          Booking requested for {timeIn(done.starts_at, timezone)} on {dayLabel(day)}. The business will confirm it soon.
        </p>
        <Link href="/bookings">See my bookings</Link>
      </div>
    );

  const service = services.find((s) => s.id === serviceId);
  return (
    <section className={styles.card} aria-labelledby="book-title">
      <h2 id="book-title" className={styles.h2}>Book a time</h2>
      <label className={styles.form}>
        <span>Service</span>
        <select className={styles.select} value={serviceId} onChange={(e) => choose({ serviceId: e.target.value })}>
          {services.map((s) => (
            <option key={s.id} value={s.id}>
              {s.name} · {rupees(s.price_paise)} · {s.duration_min} min
            </option>
          ))}
        </select>
      </label>
      <div className={styles.chips} role="group" aria-label="Day">
        {days.map((d) => (
          <button key={d} type="button" className={styles.chip} aria-pressed={d === day} onClick={() => choose({ day: d })}>
            {dayLabel(d)}
          </button>
        ))}
      </div>
      {slots.kind === "loading" ? <p className={styles.muted} aria-busy="true">Loading times…</p> : null}
      {slots.kind === "error" ? <p className={styles.alert} role="alert">{slots.message}</p> : null}
      {slots.kind === "ready" && slots.data.slots.length === 0 ? <p className={styles.empty}>No free times on this day. Try another day.</p> : null}
      {slots.kind === "ready" && slots.data.slots.length > 0 ? (
        <div className={styles.grid} role="group" aria-label="Available times">
          {slots.data.slots.map((s) => (
            <button key={s.starts_at} type="button" className={styles.chip} aria-pressed={s.starts_at === picked} onClick={() => pick(s.starts_at)}>
              {timeIn(s.starts_at, timezone)}
            </button>
          ))}
        </div>
      ) : null}
      {error ? <p className={styles.alert} role="alert">{error}</p> : null}
      <Button onClick={() => void confirm()} disabled={!picked} loading={busy}>
        {picked && service ? `Book ${timeIn(picked, timezone)} · ${rupees(service.price_paise)}` : "Pick a time"}
      </Button>
    </section>
  );
}
