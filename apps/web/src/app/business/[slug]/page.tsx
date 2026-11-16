import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { BookingWidget } from "@/features/booking/BookingWidget";
import styles from "@/features/ui.module.css";
import { serverGet } from "@/lib/api/server";
import type { BusinessPublic, ReviewPage } from "@/lib/api/types";
import { WEEKDAYS, hhmm, rupees } from "@/lib/format";

type Params = { params: Promise<{ slug: string }> };

const SITE = process.env.RSV_PUBLIC_BASE_URL ?? "http://localhost:8080";

export async function generateMetadata({ params }: Params): Promise<Metadata> {
  const { slug } = await params;
  const b = await serverGet<BusinessPublic>(`/api/v1/businesses/by-slug/${encodeURIComponent(slug)}`);
  if (!b) return { title: "Business not found" };
  const description = b.tagline ?? `${b.name} in ${b.area ?? b.city ?? "your area"} — book on RedStarVibe.`;
  // Rich WhatsApp/social preview with a generated 1200x630 share image (Blueprint 10, 23.6).
  return {
    title: b.name,
    description,
    alternates: { canonical: `${SITE}/business/${b.slug}` },
    openGraph: {
      title: b.name, description, url: `${SITE}/business/${b.slug}`, siteName: "RedStarVibe", type: "website",
      images: [{ url: `${SITE}/api/v1/og/business/${b.slug}.png`, width: 1200, height: 630, alt: b.name }],
    },
    twitter: { card: "summary_large_image", title: b.name, description, images: [`${SITE}/api/v1/og/business/${b.slug}.png`] },
  };
}

export default async function BusinessPage({ params }: Params) {
  const { slug } = await params;
  const b = await serverGet<BusinessPublic>(`/api/v1/businesses/by-slug/${encodeURIComponent(slug)}`);
  if (!b) notFound();
  const reviews = await serverGet<ReviewPage>(`/api/v1/businesses/${b.id}/reviews?limit=5`);

  return (
    <main className={styles.shell}>
      <header className={styles.topbar}>
        <Link href="/" className={styles.brand}>RedStarVibe</Link>
      </header>
      <section className={styles.hero}>
        <h1 className={styles.h1}>{b.name}</h1>
        {b.tagline ? <p>{b.tagline}</p> : null}
        <p className={styles.muted}>
          <span className={styles.badge}>{b.category.replace("_", " ")}</span> {[b.area, b.city].filter(Boolean).join(", ")}
          {reviews && reviews.count > 0 ? ` · ★ ${reviews.average} (${reviews.count})` : ""}
        </p>
      </section>

      <BookingWidget businessId={b.id} slug={b.slug} timezone={b.timezone} services={b.services} />

      <section className={styles.card} aria-labelledby="services-title">
        <h2 id="services-title" className={styles.h2}>Services</h2>
        <ul className={styles.list}>
          {b.services.map((s) => (
            <li key={s.id} className={styles.item}>
              <span>
                <strong>{s.name}</strong>
                {s.description ? <span className={styles.muted}> — {s.description}</span> : null}
              </span>
              <span className={styles.price}>{rupees(s.price_paise)} · {s.duration_min} min</span>
            </li>
          ))}
        </ul>
      </section>

      {b.description ? (
        <section className={styles.card}>
          <h2 className={styles.h2}>About</h2>
          <p style={{ margin: 0, whiteSpace: "pre-line" }}>{b.description}</p>
        </section>
      ) : null}

      <section className={styles.card} aria-labelledby="hours-title">
        <h2 id="hours-title" className={styles.h2}>Opening hours</h2>
        <ul className={styles.list}>
          {WEEKDAYS.map((label, i) => {
            const rows = b.hours.filter((h) => h.weekday === i);
            return (
              <li key={label} className={styles.item}>
                <span>{label}</span>
                <span>{rows.length ? rows.map((h) => `${hhmm(h.opens)}–${hhmm(h.closes)}`).join(", ") : "Closed"}</span>
              </li>
            );
          })}
        </ul>
      </section>

      <section className={styles.card} aria-labelledby="reviews-title">
        <h2 id="reviews-title" className={styles.h2}>Reviews</h2>
        {!reviews || reviews.items.length === 0 ? <p className={styles.muted}>No reviews yet. Reviews come only from completed bookings.</p> : null}
        <ul className={styles.list}>
          {reviews?.items.map((r) => (
            <li key={r.id} className={styles.card}>
              <span><span className={styles.stars} aria-label={`${r.rating} out of 5`}>{"★".repeat(r.rating)}</span> {r.customer_name}</span>
              {r.body ? <p style={{ margin: 0 }}>{r.body}</p> : null}
              {r.reply_body ? <p className={styles.muted}>Reply from {b.name}: {r.reply_body}</p> : null}
            </li>
          ))}
        </ul>
      </section>
    </main>
  );
}
