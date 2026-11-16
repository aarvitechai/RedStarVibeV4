"use client";

import { type ChangeEvent, type FormEvent, useCallback, useEffect, useState } from "react";
import { Button } from "@/components/ui/Button";
import { Field } from "@/components/ui/Field";
import { ApiError, api } from "@/lib/api/client";
import { uploadFile } from "@/lib/upload";
import styles from "@/features/ui.module.css";

interface Album { id: string; title: string; share_token: string | null; pages: { url: string }[]; slideshow_status: string; slideshow_url: string | null }

export function AlbumsManager() {
  const [albums, setAlbums] = useState<Album[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => api<Album[]>("/api/v1/albums/mine").then(setAlbums).catch((err: unknown) => {
    setError(err instanceof ApiError && err.status === 401 ? "Please log in to make albums." : "Could not load albums.");
  }), []);

  useEffect(() => { void load(); }, [load]);

  async function create(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const form = e.currentTarget;
    const title = new FormData(form).get("title");
    try {
      await api("/api/v1/albums", { method: "POST", body: JSON.stringify({ title }) });
      form.reset();
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not create the album.");
    }
  }

  return (
    <section className={styles.card} aria-labelledby="albums-title">
      <h1 id="albums-title" className={styles.h2}>Albums</h1>
      {error ? <p className={styles.alert} role="alert">{error}</p> : null}
      <form className={styles.formRow} onSubmit={create}>
        <Field label="New album title" name="title" required maxLength={100} />
        <Button type="submit" variant="secondary">Create album</Button>
      </form>
      {albums?.length === 0 ? <p className={styles.empty}>No albums yet.</p> : null}
      <ul className={styles.list}>
        {albums?.map((a) => <AlbumRow key={a.id} album={a} onChange={() => void load()} />)}
      </ul>
    </section>
  );
}

function AlbumRow({ album, onChange }: { album: Album; onChange: () => void }) {
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const shareUrl = album.share_token ? `${window.location.origin}/a/${album.share_token}` : "";

  useEffect(() => {
    if (album.slideshow_status !== "rendering") return;
    const t = setTimeout(onChange, 3000);
    return () => clearTimeout(t);
  }, [album.slideshow_status, onChange]);

  async function addPhotos(e: ChangeEvent<HTMLInputElement>) {
    const files = Array.from(e.target.files ?? []);
    if (!files.length) return;
    setError(null);
    try {
      const ids: string[] = [];
      for (const [i, f] of files.entries()) {
        setBusy(`Uploading ${i + 1} of ${files.length}…`);
        ids.push((await uploadFile(f, "image", "album")).id);
      }
      await api(`/api/v1/albums/${album.id}/items`, { method: "PUT", body: JSON.stringify({ asset_ids: ids }) });
      onChange();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Upload failed.");
    } finally {
      setBusy(null);
      e.target.value = "";
    }
  }

  async function slideshow() {
    try {
      await api(`/api/v1/albums/${album.id}/slideshow`, { method: "POST" });
      onChange();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not start the slideshow.");
    }
  }

  return (
    <li className={styles.card}>
      <div className={styles.row}>
        <strong>{album.title}</strong>
        <span className={styles.muted}>{album.pages.length} photos</span>
      </div>
      <label className={styles.form}>
        <span>Add photos (replaces current pages)</span>
        <input type="file" accept="image/jpeg,image/png,image/webp" multiple onChange={(e) => void addPhotos(e)} disabled={busy !== null} />
      </label>
      {busy ? <p className={styles.muted} aria-busy="true">{busy}</p> : null}
      {error ? <p className={styles.alert} role="alert">{error}</p> : null}
      {album.pages.length > 0 ? (
        <div className={styles.nav}>
          <a className={styles.navLink} href={shareUrl} target="_blank" rel="noopener noreferrer">Open flipbook</a>
          <a className={styles.navLink} href={`https://wa.me/?text=${encodeURIComponent(`${album.title} ${shareUrl}`)}`} target="_blank" rel="noopener noreferrer">Share on WhatsApp</a>
          {album.slideshow_status === "ready" && album.slideshow_url ? (
            <a className={styles.navLink} href={album.slideshow_url} download>Download slideshow</a>
          ) : (
            <Button size="sm" variant="secondary" onClick={() => void slideshow()} loading={album.slideshow_status === "rendering"}>
              {album.slideshow_status === "rendering" ? "Making slideshow…" : album.slideshow_status === "failed" ? "Retry slideshow" : "Make slideshow video"}
            </Button>
          )}
        </div>
      ) : null}
    </li>
  );
}
