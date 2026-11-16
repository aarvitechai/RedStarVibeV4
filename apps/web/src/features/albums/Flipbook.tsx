"use client";
/* eslint-disable @next/next/no-img-element -- pre-sized renditions */

import { useEffect, useState } from "react";
import { Button } from "@/components/ui/Button";
import styles from "@/features/ui.module.css";

/** Book-style album viewer: all work happens in the browser (Blueprint 9.7). */
export function Flipbook({ title, pages }: { title: string; pages: { url: string; caption: string | null }[] }) {
  const [i, setI] = useState(0);
  const last = pages.length - 1;

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "ArrowRight") setI((x) => Math.min(x + 1, last));
      if (e.key === "ArrowLeft") setI((x) => Math.max(x - 1, 0));
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [last]);

  if (pages.length === 0) return <p className={styles.empty}>This album is empty.</p>;
  const page = pages[i];
  return (
    <section className={styles.card} aria-roledescription="carousel" aria-label={title}>
      <img key={page?.url} src={page?.url} alt={page?.caption ?? `${title}, page ${i + 1}`} width={1080} height={1080}
        style={{ width: "100%", height: "auto", borderRadius: "var(--radius-card)", transition: "opacity var(--motion-base) var(--ease)" }} />
      {page?.caption ? <p className={styles.muted}>{page.caption}</p> : null}
      <div className={styles.row}>
        <Button variant="secondary" onClick={() => setI((x) => Math.max(x - 1, 0))} disabled={i === 0}>Previous</Button>
        <span aria-live="polite">{i + 1} / {pages.length}</span>
        <Button variant="secondary" onClick={() => setI((x) => Math.min(x + 1, last))} disabled={i === last}>Next</Button>
      </div>
    </section>
  );
}
