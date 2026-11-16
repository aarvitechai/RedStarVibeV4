"use client";
/* eslint-disable @next/next/no-img-element -- rendered card PNG */

import { type FormEvent, useEffect, useState } from "react";
import { Button } from "@/components/ui/Button";
import { Field } from "@/components/ui/Field";
import { ApiError, api } from "@/lib/api/client";
import { uploadFile } from "@/lib/upload";
import styles from "@/features/ui.module.css";

interface Template { id: string; occasion: string; name: string; locale: string; preview: { bg_top: string; bg_bottom: string } }
interface Card { id: string; status: string; image_url: string | null; title: string }

export function CardMaker() {
  const [templates, setTemplates] = useState<Template[]>([]);
  const [templateId, setTemplateId] = useState("");
  const [card, setCard] = useState<Card | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const c = new AbortController();
    api<Template[]>("/api/v1/cards/templates", { signal: c.signal })
      .then((t) => { setTemplates(t); setTemplateId((cur) => cur || t[0]?.id || ""); })
      .catch(() => undefined);
    return () => c.abort();
  }, []);

  useEffect(() => {
    if (!card || card.status === "ready") return;
    const timer = setTimeout(() => {
      api<Card>(`/api/v1/cards/${card.id}`).then(setCard).catch(() => undefined);
    }, 800);
    return () => clearTimeout(timer);
  }, [card]);

  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const f = new FormData(e.currentTarget);
    setBusy(true);
    setError(null);
    try {
      const photo = f.get("photo");
      let photoId: string | null = null;
      if (photo instanceof File && photo.size > 0) photoId = (await uploadFile(photo, "image", "card")).id;
      const created = await api<Card>("/api/v1/cards", {
        method: "POST",
        body: JSON.stringify({
          template_id: templateId, photo_asset_id: photoId,
          fields: { title: f.get("title"), message: f.get("message") || null, from: f.get("from") || null },
        }),
      });
      setCard(created);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not make the card.");
    } finally {
      setBusy(false);
    }
  }

  const shareUrl = card ? `${window.location.origin}/c/${card.id}` : "";
  async function share() {
    if (!card) return;
    void api(`/api/v1/cards/${card.id}/shared`, { method: "POST" }).catch(() => undefined);
    if (navigator.share) await navigator.share({ title: card.title, url: shareUrl }).catch(() => undefined);
    else window.open(`https://wa.me/?text=${encodeURIComponent(`${card.title} ${shareUrl}`)}`, "_blank", "noopener");
  }

  return (
    <section className={styles.card} aria-labelledby="cards-title">
      <h1 id="cards-title" className={styles.h2}>Make a card</h1>
      <div className={styles.chips} role="group" aria-label="Template">
        {templates.map((t) => (
          <button key={t.id} type="button" className={styles.chip} aria-pressed={t.id === templateId} onClick={() => setTemplateId(t.id)}
            style={{ backgroundImage: t.id === templateId ? undefined : `linear-gradient(${t.preview.bg_top}22, ${t.preview.bg_bottom}22)` }}>
            {t.name}
          </button>
        ))}
      </div>
      <form className={styles.form} onSubmit={submit}>
        <Field label="Title" name="title" required maxLength={60} defaultValue="Happy Birthday!" />
        <Field label="Message" name="message" maxLength={280} />
        <Field label="From" name="from" maxLength={40} />
        <label className={styles.form}>
          <span>Photo (optional)</span>
          <input type="file" name="photo" accept="image/jpeg,image/png,image/webp" />
        </label>
        {error ? <p className={styles.alert} role="alert">{error}</p> : null}
        <Button type="submit" loading={busy}>{busy ? "Making…" : "Make card"}</Button>
      </form>
      {card ? (
        <div className={styles.card} aria-live="polite">
          {card.status === "ready" && card.image_url ? (
            <>
              <img src={card.image_url} alt={card.title} width={540} height={675} style={{ width: "100%", height: "auto", borderRadius: "var(--radius-card)" }} />
              <div className={styles.nav}>
                <Button onClick={() => void share()}>Share</Button>
                <a className={styles.navLink} href={card.image_url} download={`redstarvibe-card-${card.id}.png`}>Download</a>
              </div>
              <p className={styles.share}>{shareUrl}</p>
            </>
          ) : (
            <p className={styles.muted} aria-busy="true">Creating your card…</p>
          )}
        </div>
      ) : null}
    </section>
  );
}
