"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { type FormEvent, useState } from "react";
import { Button } from "@/components/ui/Button";
import { Field } from "@/components/ui/Field";
import { ApiError, api, fieldErrors } from "@/lib/api/client";
import styles from "./auth.module.css";

export function SignupForm() {
  const router = useRouter();
  const ref = useSearchParams().get("ref");
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);

  async function onSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const form = new FormData(e.currentTarget);
    setBusy(true);
    setErrors({});
    try {
      await api("/api/v1/auth/signup", {
        method: "POST",
        body: JSON.stringify({
          username: form.get("username"),
          email: form.get("email"),
          password: form.get("password"),
          display_name: form.get("display_name"),
          is_18_or_older: form.get("is_18_or_older") === "on",
          referral_code: ref && /^[A-Za-z0-9]{1,12}$/.test(ref) ? ref : null,
        }),
      });
      router.push("/account");
      router.refresh();
    } catch (err) {
      const fields = fieldErrors(err);
      setErrors(Object.keys(fields).length ? fields : { form: err instanceof ApiError ? err.message : "Could not sign up." });
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className={styles.card} onSubmit={onSubmit} noValidate>
      <Link href="/" className={styles.brand}>RedStarVibe</Link>
      <h1 className={styles.title}>Create your account</h1>
      {errors.form ? <p className={styles.formError} role="alert">{errors.form}</p> : null}
      <Field label="Name" name="display_name" autoComplete="name" required error={errors.display_name} />
      <Field label="Username" name="username" autoComplete="username" required hint="Your page will be redstarvibe.com/username" error={errors.username} />
      <Field label="Email" name="email" type="email" autoComplete="email" required error={errors.email} />
      <Field label="Password" name="password" type="password" autoComplete="new-password" minLength={10} required hint="At least 10 characters" error={errors.password} />
      <label className={styles.check}>
        <input type="checkbox" name="is_18_or_older" required />
        <span>I am 18 or older</span>
      </label>
      <Button type="submit" loading={busy}>{busy ? "Creating account…" : "Sign up"}</Button>
      <p className={styles.muted}>
        Already have an account? <Link href="/login">Log in</Link>
      </p>
    </form>
  );
}
