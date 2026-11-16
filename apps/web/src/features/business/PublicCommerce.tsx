"use client";

import { useRouter } from "next/navigation";
import { type FormEvent, useEffect, useRef, useState } from "react";
import { Button } from "@/components/ui/Button";
import { Field } from "@/components/ui/Field";
import { ApiError, api } from "@/lib/api/client";
import { rupees } from "@/lib/format";
import styles from "@/features/ui.module.css";
import type { components } from "../../../../../packages/api-types";

type Product = components["schemas"]["ProductOut"];
type Package = components["schemas"]["PackageOut"];

export function PublicCommerce({ businessId, slug }: { businessId: string; slug: string }) {
  const router = useRouter();
  const [products, setProducts] = useState<Product[]>([]);
  const [packages, setPackages] = useState<Package[]>([]);
  const [cart, setCart] = useState<Record<string, number>>({});
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const orderKey = useRef<string>("");

  useEffect(() => {
    const c = new AbortController();
    api<Product[]>(`/api/v1/businesses/${businessId}/products`, { signal: c.signal }).then(setProducts).catch(() => undefined);
    api<Package[]>(`/api/v1/businesses/${businessId}/packages`, { signal: c.signal }).then(setPackages).catch(() => undefined);
    return () => c.abort();
  }, [businessId]);

  function handle(err: unknown) {
    if (err instanceof ApiError && err.status === 401) router.push(`/login?next=/business/${slug}`);
    else setMsg({ ok: false, text: err instanceof ApiError ? err.message : "Something went wrong." });
  }

  async function checkout(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const f = new FormData(e.currentTarget);
    const items = Object.entries(cart).filter(([, q]) => q > 0).map(([product_id, qty]) => ({ product_id, qty }));
    if (!items.length) return;
    orderKey.current ||= crypto.randomUUID(); // same key for retries of this checkout
    try {
      await api("/api/v1/orders", { method: "POST", headers: { "Idempotency-Key": orderKey.current }, body: JSON.stringify({
        business_id: businessId, items, fulfilment: f.get("fulfilment"), address: f.get("address") || null,
        wanted_on: f.get("wanted_on") || null, note: f.get("note") || null }) });
      setCart({});
      orderKey.current = "";
      setMsg({ ok: true, text: "Order placed! Track it under My orders." });
    } catch (err) {
      handle(err);
    }
  }

  async function bookPackage(e: FormEvent<HTMLFormElement>, pkg: Package) {
    e.preventDefault();
    const f = new FormData(e.currentTarget);
    try {
      await api("/api/v1/event-bookings", { method: "POST", headers: { "Idempotency-Key": crypto.randomUUID() },
        body: JSON.stringify({ package_id: pkg.id, event_date: f.get("date"), guests: Number(f.get("guests") || 1) }) });
      setMsg({ ok: true, text: `${pkg.name} is held for you for 48 hours. The organizer will confirm.` });
    } catch (err) {
      handle(err);
    }
  }

  const total = products.reduce((sum, p) => sum + (cart[p.id] ?? 0) * p.price_paise, 0);
  return (
    <>
      {msg ? <p className={msg.ok ? styles.success : styles.alert} role="status">{msg.text}</p> : null}
      {packages.length ? (
        <section className={styles.card} aria-labelledby="pkg-title">
          <h2 id="pkg-title" className={styles.h2}>Event packages</h2>
          {packages.map((p) => (
            <form key={p.id} className={styles.card} onSubmit={(e) => void bookPackage(e, p)}>
              <div className={styles.row}><strong>{p.name} <span className={styles.badge}>{p.tier}</span></strong><span className={styles.price}>{rupees(p.price_paise)}</span></div>
              <span className={styles.muted}>Up to {p.max_guests} guests · {p.items.map((i) => i.vendor ? `${i.label} by ${i.vendor}` : i.label).join(" · ")}</span>
              <div className={styles.formRow}>
                <Field label="Event date" name="date" type="date" required />
                <Field label="Guests" name="guests" type="number" min={1} max={p.max_guests} defaultValue={Math.min(100, p.max_guests)} required />
                <Button type="submit">Check & hold date</Button>
              </div>
            </form>
          ))}
        </section>
      ) : null}
      {products.length ? (
        <form className={styles.card} onSubmit={(e) => void checkout(e)} aria-labelledby="shop-title">
          <h2 id="shop-title" className={styles.h2}>Shop</h2>
          <ul className={styles.list}>
            {products.map((p) => (
              <li key={p.id} className={styles.item}>
                <span>{p.name} · <span className={styles.price}>{rupees(p.price_paise)}</span>{p.in_stock ? "" : " · sold out"}</span>
                <input type="number" min={0} max={p.stock} value={cart[p.id] ?? 0} disabled={!p.in_stock} aria-label={`Quantity of ${p.name}`}
                  className={styles.select} style={{ width: 90 }} onChange={(e) => setCart({ ...cart, [p.id]: Math.max(0, Number(e.target.value)) })} />
              </li>
            ))}
          </ul>
          <div className={styles.formRow}>
            <label className={styles.form}><span>Pickup or delivery</span>
              <select name="fulfilment" className={styles.select} defaultValue="pickup"><option value="pickup">Pickup</option><option value="delivery">Delivery</option></select>
            </label>
            <Field label="Address (for delivery)" name="address" />
            <Field label="Needed on (bulk orders)" name="wanted_on" type="date" />
          </div>
          <Field label="Note to the shop" name="note" maxLength={500} />
          <Button type="submit" disabled={total === 0}>Place order · {rupees(total)}</Button>
        </form>
      ) : null}
    </>
  );
}
