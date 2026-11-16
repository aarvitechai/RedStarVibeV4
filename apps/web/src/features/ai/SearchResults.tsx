"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { type FormEvent, useEffect, useState } from "react";
import { Button } from "@/components/ui/Button";
import { api } from "@/lib/api/client";
import styles from "@/features/ui.module.css";
import type { components } from "../../../../../packages/api-types";

type Hit = components["schemas"]["SearchHit"];

export function SearchResults() {
  const router = useRouter();
  const q = useSearchParams().get("q") ?? "";
  const [hits, setHits] = useState<Hit[] | null>(null);

  useEffect(() => {
    if (!q) return;
    const c = new AbortController();
    api<Hit[]>(`/api/v1/search?q=${encodeURIComponent(q)}`, { signal: c.signal }).then(setHits).catch(() => setHits([]));
    return () => c.abort();
  }, [q]);

  function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const next = String(new FormData(e.currentTarget).get("q") ?? "").trim();
    if (next) router.push(`/search?q=${encodeURIComponent(next)}`);
  }

  return (
    <section className={styles.card} aria-labelledby="search-title">
      <h1 id="search-title" className={styles.h2}>Search</h1>
      <form className={styles.formRow} onSubmit={submit} role="search">
        <input name="q" defaultValue={q} maxLength={200} placeholder="Businesses, posts, help…" className={styles.select} aria-label="Search" />
        <Button type="submit">Search</Button>
      </form>
      {q && hits?.length === 0 ? <p className={styles.empty}>No results for “{q}”.</p> : null}
      <ul className={styles.list}>
        {hits?.map((h) => (
          <li key={`${h.kind}-${h.source_id}`} className={styles.item}>
            <span><span className={styles.badge}>{h.kind}</span> <Link href={h.url}><strong>{h.title}</strong></Link> <span className={styles.muted}>{h.snippet}</span></span>
          </li>
        ))}
      </ul>
    </section>
  );
}
