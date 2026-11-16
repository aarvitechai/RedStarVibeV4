"use client";

import Link from "next/link";
import { useState } from "react";
import { Button } from "@/components/ui/Button";
import { ApiError, api } from "@/lib/api/client";
import type { NearbyItem } from "@/lib/api/types";
import styles from "@/features/ui.module.css";

// Pilot city fallback when the browser does not share location (Blueprint 1.3: one city first).
const PILOT = { lat: 26.9124, lng: 75.7873, name: "Jaipur" };

type State = { kind: "idle" } | { kind: "loading" } | { kind: "ready"; items: NearbyItem[]; where: string } | { kind: "error"; message: string };

export function NearbySearch() {
  const [state, setState] = useState<State>({ kind: "idle" });

  async function search(lat: number, lng: number, where: string) {
    try {
      const items = await api<NearbyItem[]>(`/api/v1/businesses/nearby?lat=${lat}&lng=${lng}&radius_km=15`);
      setState({ kind: "ready", items, where });
    } catch (err) {
      setState({ kind: "error", message: err instanceof ApiError ? err.message : "Search failed." });
    }
  }

  function nearMe() {
    setState({ kind: "loading" });
    if (!("geolocation" in navigator)) return void search(PILOT.lat, PILOT.lng, PILOT.name);
    navigator.geolocation.getCurrentPosition(
      (p) => void search(p.coords.latitude, p.coords.longitude, "you"),
      () => void search(PILOT.lat, PILOT.lng, PILOT.name),
      { timeout: 8000, maximumAge: 600_000 },
    );
  }

  return (
    <section className={styles.card} aria-labelledby="near-title" style={{ textAlign: "left" }}>
      <h2 id="near-title" className={styles.h2}>Find local services</h2>
      <Button onClick={nearMe} loading={state.kind === "loading"}>Show businesses near me</Button>
      {state.kind === "error" ? <p className={styles.alert} role="alert">{state.message}</p> : null}
      {state.kind === "ready" && state.items.length === 0 ? <p className={styles.empty}>No businesses near {state.where} yet. Be the first!</p> : null}
      {state.kind === "ready" && state.items.length > 0 ? (
        <ul className={styles.list} aria-live="polite">
          {state.items.map((b) => (
            <li key={b.id} className={styles.item}>
              <Link href={`/business/${b.slug}`}><strong>{b.name}</strong></Link>
              <span className={styles.muted}>{b.category.replace("_", " ")} · {b.distance_km.toFixed(1)} km</span>
            </li>
          ))}
        </ul>
      ) : null}
    </section>
  );
}
