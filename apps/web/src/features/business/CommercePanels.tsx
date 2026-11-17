"use client";

import { type FormEvent, useCallback, useEffect, useState } from "react";
import { Button } from "@/components/ui/Button";
import { Field } from "@/components/ui/Field";
import { ApiError, api } from "@/lib/api/client";
import type { BusinessOwnerView } from "@/lib/api/types";
import { rupees } from "@/lib/format";
import styles from "@/features/ui.module.css";
import type { components } from "../../../../../packages/api-types";

type S = components["schemas"];
type Product = S["ProductOut"];
type Order = S["OrderOut"];
type Package = S["PackageOut"];
type Vendor = S["VendorOut"];
type EventBooking = S["EventBookingOut"];

const NEXT: Record<string, string[]> = { placed: ["confirmed", "cancelled"], confirmed: ["ready", "shipped", "cancelled"], ready: ["delivered"], shipped: ["delivered"] };

function useLoad<T>(url: string): [T | null, () => void] {
  const [data, setData] = useState<T | null>(null);
  const [tick, setTick] = useState(0);
  useEffect(() => {
    const c = new AbortController();
    api<T>(url, { signal: c.signal }).then(setData).catch(() => undefined);
    return () => c.abort();
  }, [url, tick]);
  return [data, useCallback(() => setTick((t) => t + 1), [])];
}

export function ShopPanel({ biz }: { biz: BusinessOwnerView }) {
  const [products, reloadProducts] = useLoad<Product[]>(`/api/v1/businesses/${biz.id}/products`);
  const [orders, reloadOrders] = useLoad<Order[]>(`/api/v1/businesses/${biz.id}/orders`);
  const [error, setError] = useState<string | null>(null);

  async function add(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const form = e.currentTarget;
    const f = new FormData(form);
    try {
      await api(`/api/v1/businesses/${biz.id}/products`, { method: "POST", body: JSON.stringify({
        name: f.get("name"), price_paise: Math.round(Number(f.get("price") || 0) * 100), stock: Number(f.get("stock") || 0) }) });
      form.reset();
      reloadProducts();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not add the product.");
    }
  }

  async function move(id: string, status: string) {
    await api(`/api/v1/orders/${id}/status`, { method: "POST", body: JSON.stringify({ status }) }).catch((err: unknown) =>
      setError(err instanceof ApiError ? err.message : "Could not update the order."));
    reloadOrders();
    reloadProducts();
  }

  return (
    <section className={styles.card} aria-labelledby="shop-title">
      <h2 id="shop-title" className={styles.h2}>Shop</h2>
      <ul className={styles.list}>
        {products?.map((p) => (
          <li key={p.id} className={styles.item}><span>{p.name}</span><span className={styles.price}>{rupees(p.price_paise)} · stock {p.stock}</span></li>
        ))}
      </ul>
      <form className={styles.formRow} onSubmit={add}>
        <Field label="Product" name="name" required />
        <Field label="Product price (₹)" name="price" type="number" min={0} required />
        <Field label="Stock" name="stock" type="number" min={0} defaultValue={10} required />
        <Button type="submit" variant="secondary">Add product</Button>
      </form>
      {error ? <p className={styles.alert} role="alert">{error}</p> : null}
      <h3>Orders</h3>
      {orders?.length === 0 ? <p className={styles.empty}>No orders yet.</p> : null}
      <ul className={styles.list}>
        {orders?.map((o) => (
          <li key={o.id} className={styles.card}>
            <div className={styles.row}>
              <span>{o.items.map((i) => `${i.qty}× ${i.name}`).join(", ")}</span>
              <span className={styles.badge} data-status={o.status === "delivered" ? "done" : o.status === "cancelled" ? "cancelled" : "pending"}>{o.status}</span>
            </div>
            <span className={styles.muted}>{rupees(o.total_paise)} · {o.fulfilment}{o.wanted_on ? ` · for ${o.wanted_on}` : ""}{o.address ? ` · ${o.address}` : ""}{o.payment_status === "paid" ? " · paid" : ""}</span>
            {o.note ? <span className={styles.muted}>Note: {o.note}</span> : null}
            <div className={styles.nav}>
              {(NEXT[o.status] ?? []).map((s) => <Button key={s} size="sm" variant={s === "cancelled" ? "ghost" : "secondary"} onClick={() => void move(o.id, s)}>{s}</Button>)}
            </div>
          </li>
        ))}
      </ul>
    </section>
  );
}

export function EventsPanel({ biz }: { biz: BusinessOwnerView }) {
  const [packages, reloadPackages] = useLoad<Package[]>(`/api/v1/businesses/${biz.id}/packages`);
  const [vendors, reloadVendors] = useLoad<Vendor[]>(`/api/v1/businesses/${biz.id}/vendors`);
  const [bookings, reloadBookings] = useLoad<EventBooking[]>(`/api/v1/businesses/${biz.id}/event-bookings`);
  const [msg, setMsg] = useState<string | null>(null);

  async function invite(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const form = e.currentTarget;
    try {
      await api(`/api/v1/businesses/${biz.id}/vendors`, { method: "POST", body: JSON.stringify({ vendor_slug: new FormData(form).get("slug") }) });
      form.reset();
      reloadVendors();
    } catch (err) {
      setMsg(err instanceof ApiError ? err.message : "Could not invite.");
    }
  }

  async function answer(org: string, decision: "accept" | "decline") {
    await api(`/api/v1/businesses/${biz.id}/vendor-invites/${org}/${decision}`, { method: "POST" }).catch(() => undefined);
    reloadVendors();
  }

  async function addPackage(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const form = e.currentTarget;
    const f = new FormData(form);
    const vendorSlugs = String(f.get("vendors") ?? "").split(",").map((s) => s.trim()).filter(Boolean);
    try {
      await api(`/api/v1/businesses/${biz.id}/packages`, { method: "POST", body: JSON.stringify({
        name: f.get("name"), tier: f.get("tier"), price_paise: Math.round(Number(f.get("price") || 0) * 100),
        max_guests: Number(f.get("guests") || 1), items: [{ label: "Venue & setup" }, ...vendorSlugs.map((v) => ({ label: v, vendor_slug: v }))] }) });
      form.reset();
      reloadPackages();
    } catch (err) {
      setMsg(err instanceof ApiError ? err.message : "Could not create the package.");
    }
  }

  async function setStatus(id: string, status: string) {
    await api(`/api/v1/event-bookings/${id}/status`, { method: "POST", body: JSON.stringify({ status }) }).catch(() => undefined);
    reloadBookings();
  }

  const invites = vendors?.filter((v) => v.vendor === biz.slug && v.status === "invited") ?? [];
  return (
    <section className={styles.card} aria-labelledby="events-title">
      <h2 id="events-title" className={styles.h2}>Events & packages</h2>
      {invites.map((v) => (
        <div key={v.organizer} className={styles.item}>
          <span>{v.organizer} invited you as a vendor</span>
          <span className={styles.nav}><Button size="sm" onClick={() => void answer(v.organizer, "accept")}>Accept</Button><Button size="sm" variant="ghost" onClick={() => void answer(v.organizer, "decline")}>Decline</Button></span>
        </div>
      ))}
      <ul className={styles.list}>
        {packages?.map((p) => (
          <li key={p.id} className={styles.item}><span><strong>{p.name}</strong> <span className={styles.badge}>{p.tier}</span> · up to {p.max_guests} guests</span><span className={styles.price}>{rupees(p.price_paise)}</span></li>
        ))}
      </ul>
      <form className={styles.form} onSubmit={addPackage}>
        <div className={styles.formRow}>
          <Field label="Package name" name="name" required />
          <label className={styles.form}><span>Tier</span>
            <select name="tier" className={styles.select} defaultValue="gold">
              {["silver", "gold", "platinum", "custom"].map((t) => <option key={t} value={t}>{t}</option>)}
            </select>
          </label>
          <Field label="Package price (₹)" name="price" type="number" min={0} required />
          <Field label="Max guests" name="guests" type="number" min={1} defaultValue={200} required />
        </div>
        <Field label="Vendors in this package" name="vendors" hint="Comma-separated page addresses of vendors who accepted your invite" />
        <Button type="submit" variant="secondary">Create package</Button>
      </form>
      <form className={styles.formRow} onSubmit={invite}>
        <Field label="Invite a vendor (page address)" name="slug" required />
        <Button type="submit" variant="secondary">Invite</Button>
      </form>
      <p className={styles.muted}>Vendor network: {vendors?.filter((v) => v.organizer === biz.slug).map((v) => `${v.vendor} (${v.status})`).join(", ") || "none yet"}</p>
      {msg ? <p className={styles.alert} role="alert">{msg}</p> : null}
      <h3>Event bookings</h3>
      <ul className={styles.list}>
        {bookings?.map((b) => (
          <li key={b.id} className={styles.item}>
            <span>{b.event_date} · {b.package_name} · {b.guests} guests <span className={styles.badge} data-status={b.status}>{b.status}</span></span>
            <span className={styles.nav}>
              {b.status === "pending" ? <Button size="sm" onClick={() => void setStatus(b.id, "confirmed")}>Confirm</Button> : null}
              {b.status === "pending" || b.status === "confirmed" ? <Button size="sm" variant="ghost" onClick={() => void setStatus(b.id, "cancelled")}>Cancel</Button> : null}
            </span>
          </li>
        ))}
      </ul>
    </section>
  );
}
