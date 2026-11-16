"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { ApiError, api } from "@/lib/api/client";
import type { NotificationPage } from "@/lib/api/types";
import { dateTimeIn } from "@/lib/format";
import styles from "@/features/ui.module.css";

export function NotificationsList() {
  const router = useRouter();
  const [page, setPage] = useState<NotificationPage | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const c = new AbortController();
    api<NotificationPage>("/api/v1/notifications", { signal: c.signal })
      .then(setPage)
      .catch((err: unknown) => {
        if (c.signal.aborted) return;
        if (err instanceof ApiError && err.status === 401) router.replace("/login?next=/notifications");
        else setError(err instanceof ApiError ? err.message : "Could not load notifications.");
      });
    return () => c.abort();
  }, [router]);

  async function open(id: string, link: string | null | undefined) {
    await api(`/api/v1/notifications/${id}/read`, { method: "POST" }).catch(() => undefined);
    if (link) router.push(link);
  }

  return (
    <section className={styles.card} aria-labelledby="n-title">
      <h1 id="n-title" className={styles.h2}>Notifications{page && page.unread > 0 ? ` (${page.unread} new)` : ""}</h1>
      {error ? <p className={styles.alert} role="alert">{error}</p> : null}
      {!page && !error ? <p className={styles.muted} aria-busy="true">Loading…</p> : null}
      {page?.items.length === 0 ? <p className={styles.empty}>Nothing yet. <Link href="/">Find a business</Link></p> : null}
      <ul className={styles.list}>
        {page?.items.map((n) => (
          <li key={n.id}>
            <button type="button" className={styles.item} style={{ width: "100%", textAlign: "left", background: "none", font: "inherit", cursor: "pointer", fontWeight: n.read_at ? 400 : 700 }}
              onClick={() => void open(n.id, n.link)}>
              <span>{n.title}{n.body ? <span className={styles.muted}> · {n.body}</span> : null}</span>
              <span className={styles.muted}>{dateTimeIn(n.created_at, "Asia/Kolkata")}</span>
            </button>
          </li>
        ))}
      </ul>
    </section>
  );
}
