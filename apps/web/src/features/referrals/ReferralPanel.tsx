"use client";
/* eslint-disable @next/next/no-img-element -- QR SVG from our API */

import { useEffect, useState } from "react";
import { api } from "@/lib/api/client";
import styles from "@/features/ui.module.css";

interface Summary { code: string; link: string; invited: number; qualified: number; points: number }

export function ReferralPanel() {
  const [s, setS] = useState<Summary | null>(null);
  useEffect(() => {
    const c = new AbortController();
    api<Summary>("/api/v1/referrals/me", { signal: c.signal }).then(setS).catch(() => undefined);
    return () => c.abort();
  }, []);
  if (!s) return null;
  const path = `/signup?ref=${s.code}`;
  return (
    <section className={styles.card} aria-labelledby="ref-title">
      <h2 id="ref-title" className={styles.h2}>Invite friends · {s.points} Star Points</h2>
      <p className={styles.muted}>Friends who join with your link and make a booking earn you 30 points (they get 20).</p>
      <p className={styles.share}>{s.link}</p>
      <div className={styles.nav}>
        <a className={styles.navLink} href={`https://wa.me/?text=${encodeURIComponent(`Join me on RedStarVibe: ${s.link}`)}`} target="_blank" rel="noopener noreferrer">Share on WhatsApp</a>
        <button type="button" className={styles.navLink} style={{ background: "none", border: 0, font: "inherit", cursor: "pointer" }}
          onClick={() => void navigator.clipboard.writeText(s.link)}>Copy link</button>
      </div>
      <img src={`/api/v1/qr.svg?path=${encodeURIComponent(path)}`} alt="QR code for your invite link" width={160} height={160} />
      <p className={styles.muted}>Invited: {s.invited} · Joined and active: {s.qualified}</p>
    </section>
  );
}
