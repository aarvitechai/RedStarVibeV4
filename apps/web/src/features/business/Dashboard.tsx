"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { type FormEvent, useCallback, useEffect, useState } from "react";
import { Button } from "@/components/ui/Button";
import { Field } from "@/components/ui/Field";
import { ApiError, api, fieldErrors } from "@/lib/api/client";
import type { Booking, BusinessOwnerView, Service } from "@/lib/api/types";
import { WEEKDAYS, dayLabel, hhmm, isoDateIn, rupees, timeIn } from "@/lib/format";
import styles from "@/features/ui.module.css";
import { EventsPanel, ShopPanel } from "./CommercePanels";

const CATEGORIES = ["electrician", "plumber", "welder", "driver", "carpenter", "painter", "beauty", "tailor", "tutor",
  "home_food", "bakery", "shop", "photographer", "event", "other"] as const;

type Load = { kind: "loading" } | { kind: "ready"; businesses: BusinessOwnerView[] } | { kind: "error"; message: string };

async function fetchMine(signal?: AbortSignal): Promise<Load | "signed_out"> {
  try {
    return { kind: "ready", businesses: await api<BusinessOwnerView[]>("/api/v1/businesses/mine", { signal }) };
  } catch (err) {
    if (err instanceof ApiError && err.status === 401) return "signed_out";
    return { kind: "error", message: err instanceof ApiError ? err.message : "Could not load your business." };
  }
}

export function Dashboard() {
  const router = useRouter();
  const [state, setState] = useState<Load>({ kind: "loading" });

  const reload = useCallback(
    (signal?: AbortSignal) =>
      fetchMine(signal).then((next) => {
        if (signal?.aborted) return;
        if (next === "signed_out") router.replace("/login?next=/dashboard");
        else setState(next);
      }),
    [router],
  );

  useEffect(() => {
    const c = new AbortController();
    void reload(c.signal);
    return () => c.abort();
  }, [reload]);

  if (state.kind === "loading") return <p className={styles.muted} aria-busy="true">Loading…</p>;
  if (state.kind === "error") return <p className={styles.alert} role="alert">{state.message}</p>;
  const biz = state.businesses[0];
  if (!biz) return <CreateBusiness onCreated={() => void reload()} />;
  return <Manage biz={biz} onChange={() => void reload()} />;
}

function CreateBusiness({ onCreated }: { onCreated: () => void }) {
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);

  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const f = new FormData(e.currentTarget);
    setBusy(true);
    setErrors({});
    try {
      const biz = await api<BusinessOwnerView>("/api/v1/businesses", {
        method: "POST",
        body: JSON.stringify({
          slug: f.get("slug"), name: f.get("name"), category: f.get("category"), tagline: f.get("tagline") || null,
          phone: f.get("phone") || null, area: f.get("area") || null, city: f.get("city") || null,
        }),
      });
      // Sensible defaults so the page is bookable at once: Mon–Sat 09:00–18:00.
      await api(`/api/v1/businesses/${biz.id}/hours`, {
        method: "PUT",
        body: JSON.stringify([0, 1, 2, 3, 4, 5].map((weekday) => ({ weekday, opens: "09:00", closes: "18:00" }))),
      });
      onCreated();
    } catch (err) {
      const fe = fieldErrors(err);
      setErrors(Object.keys(fe).length ? fe : { form: err instanceof ApiError ? err.message : "Could not create the page." });
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className={styles.card} onSubmit={submit} noValidate>
      <h1 className={styles.h2}>Create your business page</h1>
      <p className={styles.muted}>It takes about two minutes. You can change everything later.</p>
      {errors.form ? <p className={styles.alert} role="alert">{errors.form}</p> : null}
      <Field label="Business name" name="name" required error={errors.name} />
      <Field label="Page address" name="slug" required hint="redstarvibe.com/business/your-name" error={errors.slug} />
      <label className={styles.form}>
        <span>Category</span>
        <select name="category" className={styles.select} defaultValue="electrician">
          {CATEGORIES.map((c) => <option key={c} value={c}>{c.replace("_", " ")}</option>)}
        </select>
      </label>
      <Field label="Tagline" name="tagline" hint="One line customers see first" error={errors.tagline} />
      <div className={styles.formRow}>
        <Field label="Phone" name="phone" type="tel" autoComplete="tel" error={errors.phone} />
        <Field label="Area" name="area" error={errors.area} />
        <Field label="City" name="city" error={errors.city} />
      </div>
      <Button type="submit" loading={busy}>{busy ? "Creating…" : "Create page"}</Button>
    </form>
  );
}

function Manage({ biz, onChange }: { biz: BusinessOwnerView; onChange: () => void }) {
  const pageUrl = typeof window !== "undefined" ? `${window.location.origin}/business/${biz.slug}` : `/business/${biz.slug}`;
  return (
    <>
      <section className={styles.card}>
        <div className={styles.row}>
          <h1 className={styles.h2}>{biz.name}</h1>
          <Link href={`/business/${biz.slug}`}>View public page</Link>
        </div>
        <p className={styles.share}>Share your page: {pageUrl}</p>
        <a className={styles.navLink} href={`https://wa.me/?text=${encodeURIComponent(`Book ${biz.name} on RedStarVibe: ${pageUrl}`)}`}
          target="_blank" rel="noopener noreferrer">Share on WhatsApp</a>
        {/* eslint-disable-next-line @next/next/no-img-element -- QR SVG from our API */}
        <img src={`/api/v1/qr.svg?path=${encodeURIComponent(`/business/${biz.slug}`)}`} alt={`QR code for ${biz.name}`} width={160} height={160} />
        <p className={styles.muted}>Print this QR for your shop counter.</p>
      </section>
      <BookingsPanel biz={biz} />
      <ShopPanel biz={biz} />
      <EventsPanel biz={biz} />
      <ServicesPanel biz={biz} onChange={onChange} />
      <HoursPanel biz={biz} onChange={onChange} />
    </>
  );
}

function BookingsPanel({ biz }: { biz: BusinessOwnerView }) {
  const days = Array.from({ length: 7 }, (_, i) => isoDateIn(biz.timezone, i));
  const [day, setDay] = useState(days[0] ?? "");
  const [items, setItems] = useState<Booking[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [tick, setTick] = useState(0);

  useEffect(() => {
    const c = new AbortController();
    api<Booking[]>(`/api/v1/businesses/${biz.id}/bookings?date=${day}`, { signal: c.signal })
      .then((rows) => { setItems(rows); setError(null); })
      .catch((err: unknown) => { if (!c.signal.aborted) setError(err instanceof ApiError ? err.message : "Could not load bookings."); });
    return () => c.abort();
  }, [biz.id, day, tick]);

  async function act(id: string, action: "confirm" | "complete" | "cancel") {
    try {
      await api(`/api/v1/bookings/${id}/${action}`, { method: "POST" });
      setTick((t) => t + 1);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Action failed.");
    }
  }

  return (
    <section className={styles.card} aria-labelledby="bk-title">
      <h2 id="bk-title" className={styles.h2}>Bookings</h2>
      <div className={styles.chips} role="group" aria-label="Day">
        {days.map((d) => (
          <button key={d} type="button" className={styles.chip} aria-pressed={d === day} onClick={() => { setDay(d); setItems(null); }}>
            {dayLabel(d)}
          </button>
        ))}
      </div>
      {error ? <p className={styles.alert} role="alert">{error}</p> : null}
      {items === null ? <p className={styles.muted} aria-busy="true">Loading…</p> : null}
      {items?.length === 0 ? <p className={styles.empty}>No bookings on this day.</p> : null}
      <ul className={styles.list}>
        {items?.map((b) => (
          <li key={b.id} className={styles.item}>
            <span>
              <strong>{timeIn(b.starts_at, biz.timezone)}</strong> {b.service_name} <span className={styles.badge} data-status={b.status}>{b.status}</span>
              {b.customer_note ? <span className={styles.muted}> — {b.customer_note}</span> : null}
            </span>
            <span className={styles.nav}>
              {b.status === "pending" ? <Button size="sm" onClick={() => void act(b.id, "confirm")}>Confirm</Button> : null}
              {b.status === "confirmed" ? <Button size="sm" variant="secondary" onClick={() => void act(b.id, "complete")}>Mark done</Button> : null}
              {b.status === "pending" || b.status === "confirmed" ? <Button size="sm" variant="ghost" onClick={() => void act(b.id, "cancel")}>Cancel</Button> : null}
            </span>
          </li>
        ))}
      </ul>
    </section>
  );
}

function ServicesPanel({ biz, onChange }: { biz: BusinessOwnerView; onChange: () => void }) {
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);

  async function add(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const form = e.currentTarget;
    const f = new FormData(form);
    setBusy(true);
    setErrors({});
    try {
      await api<Service>(`/api/v1/businesses/${biz.id}/services`, {
        method: "POST",
        body: JSON.stringify({
          name: f.get("name"),
          price_paise: Math.round(Number(f.get("price") || 0) * 100),
          duration_min: Number(f.get("duration") || 0),
          buffer_min: Number(f.get("buffer") || 0),
        }),
      });
      form.reset();
      onChange();
    } catch (err) {
      const fe = fieldErrors(err);
      setErrors(Object.keys(fe).length ? fe : { form: err instanceof ApiError ? err.message : "Could not add the service." });
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className={styles.card} aria-labelledby="svc-title">
      <h2 id="svc-title" className={styles.h2}>Services</h2>
      {biz.services.length === 0 ? <p className={styles.empty}>Add your first service so customers can book.</p> : null}
      <ul className={styles.list}>
        {biz.services.map((s) => (
          <li key={s.id} className={styles.item}>
            <span>{s.name}{s.active ? "" : " (hidden)"}</span>
            <span className={styles.price}>{rupees(s.price_paise)} · {s.duration_min} min</span>
          </li>
        ))}
      </ul>
      <form className={styles.form} onSubmit={add} noValidate>
        {errors.form ? <p className={styles.alert} role="alert">{errors.form}</p> : null}
        <Field label="Service name" name="name" required error={errors.name} />
        <div className={styles.formRow}>
          <Field label="Price (₹)" name="price" type="number" min={0} step="1" required error={errors.price_paise} />
          <Field label="Duration (min)" name="duration" type="number" min={5} step="5" defaultValue={60} required error={errors.duration_min} />
          <Field label="Gap after (min)" name="buffer" type="number" min={0} step="5" defaultValue={0} hint="Travel or cleanup" error={errors.buffer_min} />
        </div>
        <Button type="submit" variant="secondary" loading={busy}>Add service</Button>
      </form>
    </section>
  );
}

function HoursPanel({ biz, onChange }: { biz: BusinessOwnerView; onChange: () => void }) {
  const first = biz.hours[0];
  const [open, setOpen] = useState(first ? hhmm(first.opens) : "09:00");
  const [close, setClose] = useState(first ? hhmm(first.closes) : "18:00");
  const [days, setDays] = useState<number[]>(() => Array.from(new Set(biz.hours.map((h) => h.weekday))));
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);

  async function save() {
    try {
      await api(`/api/v1/businesses/${biz.id}/hours`, {
        method: "PUT",
        body: JSON.stringify(days.map((weekday) => ({ weekday, opens: open, closes: close }))),
      });
      setMsg({ ok: true, text: "Hours saved." });
      onChange();
    } catch (err) {
      setMsg({ ok: false, text: err instanceof ApiError ? err.message : "Could not save hours." });
    }
  }

  return (
    <section className={styles.card} aria-labelledby="hours-title">
      <h2 id="hours-title" className={styles.h2}>Opening hours</h2>
      <div className={styles.chips} role="group" aria-label="Open days">
        {WEEKDAYS.map((label, i) => (
          <button key={label} type="button" className={styles.chip} aria-pressed={days.includes(i)}
            onClick={() => setDays((d) => (d.includes(i) ? d.filter((x) => x !== i) : [...d, i].sort()))}>
            {label}
          </button>
        ))}
      </div>
      <div className={styles.formRow}>
        <Field label="Opens" type="time" value={open} onChange={(e) => setOpen(e.target.value)} />
        <Field label="Closes" type="time" value={close} onChange={(e) => setClose(e.target.value)} />
      </div>
      {msg ? <p className={msg.ok ? styles.success : styles.alert} role="status">{msg.text}</p> : null}
      <Button variant="secondary" onClick={() => void save()}>Save hours</Button>
    </section>
  );
}
