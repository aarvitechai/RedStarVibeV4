"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { type FormEvent, useState } from "react";
import { Button } from "@/components/ui/Button";
import { ApiError, api } from "@/lib/api/client";
import styles from "@/features/ui.module.css";
import type { components } from "../../../../../packages/api-types";

type Answer = components["schemas"]["AnswerOut"];

export function Assistant() {
  const router = useRouter();
  const [answer, setAnswer] = useState<Answer | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function ask(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const question = String(new FormData(e.currentTarget).get("q") ?? "").trim();
    if (!question) return;
    setBusy(true);
    setError(null);
    try {
      setAnswer(await api<Answer>("/api/v1/ai/assistant", { method: "POST", body: JSON.stringify({ question }) }));
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) router.push("/login?next=/assistant");
      else setError(err instanceof ApiError ? err.message : "The assistant is unavailable right now.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className={styles.card} aria-labelledby="ai-title">
      <h1 id="ai-title" className={styles.h2}>Vibe AI assistant</h1>
      <p className={styles.muted}>Answers come only from help articles, your own posts and your own business data, with sources. It never reads your messages.</p>
      <form className={styles.formRow} onSubmit={(e) => void ask(e)}>
        <input name="q" maxLength={500} placeholder="e.g. What bookings do I have tomorrow?" className={styles.select} aria-label="Question" />
        <Button type="submit" loading={busy}>Ask</Button>
      </form>
      {error ? <p className={styles.alert} role="alert">{error}</p> : null}
      {answer ? (
        <div className={styles.card} aria-live="polite">
          <p style={{ margin: 0, whiteSpace: "pre-line" }}>{answer.answer}</p>
          {answer.citations.length ? (
            <ol className={styles.list}>
              {answer.citations.map((c) => <li key={c.n}>[{c.n}] <Link href={c.url}>{c.title}</Link></li>)}
            </ol>
          ) : null}
          <span className={styles.badge}>{answer.mode === "generated" ? "AI answer — check the sources" : answer.mode === "extractive" ? "From help articles" : "No answer"}</span>
        </div>
      ) : null}
    </section>
  );
}
