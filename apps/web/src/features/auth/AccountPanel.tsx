"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { Button } from "@/components/ui/Button";
import { ApiError, api } from "@/lib/api/client";
import type { Me, SessionInfo } from "@/lib/api/types";
import styles from "./auth.module.css";

type State =
  | { kind: "loading" }
  | { kind: "ready"; me: Me; sessions: SessionInfo[] }
  | { kind: "error"; message: string };

async function fetchAccount(signal?: AbortSignal): Promise<State | "signed_out"> {
  try {
    const [me, sessions] = await Promise.all([
      api<Me>("/api/v1/auth/me", { signal }),
      api<SessionInfo[]>("/api/v1/auth/sessions", { signal }),
    ]);
    return { kind: "ready", me, sessions };
  } catch (err) {
    if (err instanceof ApiError && err.status === 401) return "signed_out";
    return { kind: "error", message: err instanceof ApiError ? err.message : "Could not load your account." };
  }
}

export function AccountPanel() {
  const router = useRouter();
  const [state, setState] = useState<State>({ kind: "loading" });

  const load = useCallback(
    (signal?: AbortSignal) =>
      fetchAccount(signal).then((next) => {
        if (signal?.aborted) return;
        if (next === "signed_out") router.replace("/login?expired=1&next=/account");
        else setState(next);
      }),
    [router],
  );

  useEffect(() => {
    const controller = new AbortController();
    void load(controller.signal);
    return () => controller.abort();
  }, [load]);

  async function logout() {
    await api("/api/v1/auth/logout", { method: "POST" }).catch(() => undefined);
    router.replace("/login");
  }

  async function logoutOthers() {
    await api("/api/v1/auth/sessions/logout-others", { method: "POST" });
    await load();
  }

  if (state.kind === "loading") return <div className={styles.card} aria-busy="true">Loading your account…</div>;
  if (state.kind === "error")
    return (
      <div className={styles.card}>
        <p className={styles.formError} role="alert">{state.message}</p>
        <Button variant="secondary" onClick={() => void load()}>Try again</Button>
      </div>
    );

  const { me, sessions } = state;
  return (
    <section className={styles.card} aria-labelledby="account-title">
      <Link href="/" className={styles.brand}>RedStarVibe</Link>
      <h1 id="account-title" className={styles.title}>Hi, {me.display_name}</h1>
      <p className={styles.muted}>@{me.username} · {me.email} · {me.role}</p>
      <h2>Signed-in devices</h2>
      <ul className={styles.list}>
        {sessions.map((s) => (
          <li key={s.family_id} className={styles.row}>
            <span>{s.user_agent ?? "Unknown device"}</span>
            <span>{s.current ? "This device" : new Date(s.created_at).toLocaleDateString()}</span>
          </li>
        ))}
      </ul>
      <div className={styles.actions}>
        {sessions.length > 1 ? <Button variant="secondary" onClick={() => void logoutOthers()}>Log out other devices</Button> : null}
        <Button variant="ghost" onClick={() => void logout()}>Log out</Button>
      </div>
    </section>
  );
}
