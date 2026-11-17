"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { type FormEvent, useState } from "react";
import { Button } from "@/components/ui/Button";
import { Field } from "@/components/ui/Field";
import { ApiError, api } from "@/lib/api/client";
import styles from "./auth.module.css";

export function LoginForm() {
  const router = useRouter();
  const params = useSearchParams();
  const [error, setError] = useState<string | null>(params.get("expired") ? "Your session ended. Please log in again." : null);
  const [busy, setBusy] = useState(false);
  const [ticket, setTicket] = useState<string | null>(null);

  async function onSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const form = new FormData(e.currentTarget);
    setBusy(true);
    setError(null);
    try {
      if (ticket) {
        await api("/api/v1/auth/login/mfa", { method: "POST", body: JSON.stringify({ ticket, code: form.get("code") }) });
      } else {
        await api("/api/v1/auth/login", {
          method: "POST",
          body: JSON.stringify({ email: form.get("email"), password: form.get("password") }),
        });
      }
      const next = params.get("next");
      router.push(next && next.startsWith("/") && !next.startsWith("//") ? next : "/account");
      router.refresh();
    } catch (err) {
      if (err instanceof ApiError && err.body.code === "mfa_required") {
        setTicket(String(err.body.details.ticket));
        setError(null);
        return;
      }
      if (err instanceof ApiError && err.body.code === "mfa_ticket_invalid") setTicket(null);
      setError(err instanceof ApiError ? err.message : "Could not log in.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className={styles.card} onSubmit={onSubmit}>
      <Link href="/" className={styles.brand}>RedStarVibe</Link>
      <h1 className={styles.title}>Log in</h1>
      {error ? <p className={styles.formError} role="alert">{error}</p> : null}
      {ticket ? (
        <Field label="Code from your authenticator app" name="code" inputMode="numeric" autoComplete="one-time-code" pattern="[0-9]{6}" required autoFocus />
      ) : (
        <>
          <Field label="Email" name="email" type="email" autoComplete="email" required />
          <Field label="Password" name="password" type="password" autoComplete="current-password" required />
        </>
      )}
      <Button type="submit" loading={busy}>{busy ? "Logging in…" : "Log in"}</Button>
      <p className={styles.muted}>
        New here? <Link href="/signup">Create an account</Link>
      </p>
    </form>
  );
}
