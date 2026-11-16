"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { type FormEvent, useCallback, useEffect, useRef, useState } from "react";
import { Button } from "@/components/ui/Button";
import { ApiError, api } from "@/lib/api/client";
import type { Me } from "@/lib/api/types";
import { timeIn } from "@/lib/format";
import { uploadFile } from "@/lib/upload";
import styles from "@/features/ui.module.css";
import type { ChatMessage, Conversation } from "../posts/types";

type Frame =
  | { type: "hello" | "ping" }
  | { type: "message.new"; message: ChatMessage }
  | { type: "typing"; conversation_id: string; user_id: string }
  | { type: "receipt.read"; conversation_id: string; user_id: string; seq: number };

/**
 * Live chat. Messages are persisted by REST first; the WebSocket only pushes. On (re)connect we fetch
 * everything after the last seq we hold, so nothing is lost while offline (Blueprint 9.4).
 */
export function Messages() {
  const router = useRouter();
  const params = useSearchParams();
  const [me, setMe] = useState<Me | null>(null);
  const [convs, setConvs] = useState<Conversation[]>([]);
  const [active, setActive] = useState<string | null>(params.get("c"));
  const [msgs, setMsgs] = useState<ChatMessage[]>([]);
  const [typing, setTyping] = useState<string | null>(null);
  const [online, setOnline] = useState(false);
  const lastSeq = useRef(0);
  const activeRef = useRef(active);
  useEffect(() => {
    activeRef.current = active;
  }, [active]);

  const loadConvs = useCallback(() => api<Conversation[]>("/api/v1/chat/conversations").then(setConvs).catch((err: unknown) => {
    if (err instanceof ApiError && err.status === 401) router.replace("/login?next=/messages");
  }), [router]);

  const catchUp = useCallback(async (convId: string) => {
    const after = lastSeq.current;
    const rows = await api<ChatMessage[]>(`/api/v1/chat/conversations/${convId}/messages${after ? `?after_seq=${after}` : ""}`);
    if (activeRef.current !== convId) return;
    setMsgs((cur) => {
      const seen = new Set(cur.map((m) => m.seq));
      const merged = [...cur, ...rows.filter((m) => !seen.has(m.seq))].sort((a, b) => a.seq - b.seq);
      lastSeq.current = merged.at(-1)?.seq ?? 0;
      return merged;
    });
    if (rows.length) void api(`/api/v1/chat/conversations/${convId}/read`, { method: "POST", body: JSON.stringify({ seq: rows.at(-1)?.seq }) });
  }, []);

  useEffect(() => {
    void api<Me>("/api/v1/auth/me").then(setMe).catch(() => undefined);
    void loadConvs();
  }, [loadConvs]);

  useEffect(() => {
    if (active) void catchUp(active);
  }, [active, catchUp]);

  function open(id: string) {
    activeRef.current = id;
    lastSeq.current = 0;
    setMsgs([]);
    setActive(id);
  }

  // WebSocket with reconnect + backoff; every listener and timer is cleaned up (Blueprint 27.3).
  useEffect(() => {
    let ws: WebSocket | null = null;
    let retry = 0;
    let timer: ReturnType<typeof setTimeout> | undefined;
    let closed = false;
    const connect = () => {
      ws = new WebSocket(`${location.protocol === "https:" ? "wss" : "ws"}://${location.host}/ws`);
      ws.onopen = () => { retry = 0; setOnline(true); if (activeRef.current) void catchUp(activeRef.current); };
      ws.onmessage = (ev) => {
        const f = JSON.parse(String(ev.data)) as Frame;
        if (f.type === "ping") ws?.send(JSON.stringify({ type: "pong" }));
        if (f.type === "message.new") {
          if (f.message.conversation_id === activeRef.current) void catchUp(f.message.conversation_id);
          void loadConvs();
        }
        if (f.type === "typing" && f.conversation_id === activeRef.current) {
          setTyping(f.user_id);
          setTimeout(() => setTyping(null), 3000);
        }
      };
      ws.onclose = async (ev) => {
        setOnline(false);
        if (closed) return;
        if (ev.code === 4401) await api("/api/v1/auth/refresh", { method: "POST" }).catch(() => router.replace("/login?next=/messages"));
        timer = setTimeout(connect, Math.min(30_000, 1000 * 2 ** retry++) + Math.random() * 500);
      };
    };
    connect();
    return () => { closed = true; clearTimeout(timer); ws?.close(); };
  }, [catchUp, loadConvs, router]);

  async function send(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (!active) return;
    const form = e.currentTarget;
    const body = String(new FormData(form).get("body") ?? "").trim();
    if (!body) return;
    form.reset();
    await api(`/api/v1/chat/conversations/${active}/messages`, { method: "POST", body: JSON.stringify({ body, client_id: crypto.randomUUID() }) });
    await catchUp(active);
  }

  const lastTyping = useRef(0);
  function onType() {
    if (!active || Date.now() - lastTyping.current < 3000) return;
    lastTyping.current = Date.now();
    void api(`/api/v1/chat/conversations/${active}/typing`, { method: "POST" }).catch(() => undefined);
  }

  const conv = convs.find((c) => c.id === active);
  return (
    <section className={styles.card} aria-labelledby="msg-title">
      <div className={styles.row}>
        <h1 id="msg-title" className={styles.h2}>Messages</h1>
        <span className={styles.badge} data-status={online ? "confirmed" : "pending"}>{online ? "live" : "reconnecting"}</span>
      </div>
      <div className={styles.chips} role="tablist" aria-label="Conversations">
        {convs.map((c) => (
          <button key={c.id} type="button" role="tab" aria-selected={c.id === active} className={styles.chip} onClick={() => open(c.id)}>
            {c.title}{c.unread ? ` (${c.unread})` : ""}
          </button>
        ))}
      </div>
      {convs.length === 0 ? <p className={styles.empty}>No conversations yet. Open a profile and tap Message.</p> : null}
      {conv ? (
        <>
          <ol className={styles.list} aria-live="polite" style={{ maxHeight: "50dvh", overflowY: "auto" }}>
            {msgs.map((m) => {
              const mine = m.sender_id === me?.id;
              const who = conv.members.find((x) => x.user_id === m.sender_id)?.display_name ?? "";
              return (
                <li key={m.seq} className={styles.item} style={{ justifyContent: mine ? "flex-end" : "flex-start", background: mine ? "var(--color-primary-soft)" : undefined }}>
                  <span>
                    {!mine && conv.kind === "group" ? <strong>{who}: </strong> : null}
                    {m.body}
                    {m.attachment?.kind === "audio" ? <audio controls src={m.attachment.urls["audio.m4a"]} /> : null}
                    <span className={styles.muted}> · {timeIn(m.created_at, "Asia/Kolkata")}</span>
                  </span>
                </li>
              );
            })}
          </ol>
          {typing ? <p className={styles.muted}>{conv.members.find((x) => x.user_id === typing)?.display_name ?? "Someone"} is typing…</p> : null}
          <form className={styles.formRow} onSubmit={(e) => void send(e)}>
            <input name="body" maxLength={4000} placeholder="Message" className={styles.select} onInput={onType} aria-label="Message" autoComplete="off" />
            <Button type="submit">Send</Button>
            <VoiceNote convId={conv.id} onSent={() => void catchUp(conv.id)} />
          </form>
        </>
      ) : null}
    </section>
  );
}

function VoiceNote({ convId, onSent }: { convId: string; onSent: () => void }) {
  const [rec, setRec] = useState<MediaRecorder | null>(null);
  const [busy, setBusy] = useState(false);

  async function toggle() {
    if (rec) return rec.stop();
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true }).catch(() => null);
    if (!stream) return;
    const chunks: Blob[] = [];
    const r = new MediaRecorder(stream);
    r.ondataavailable = (e) => chunks.push(e.data);
    r.onstop = async () => {
      stream.getTracks().forEach((t) => t.stop());
      setRec(null);
      setBusy(true);
      try {
        const type = r.mimeType.split(";")[0] || "audio/webm";
        const file = new File(chunks, "voice.webm", { type });
        const asset = await uploadFile(file, "audio", "voice");
        await api(`/api/v1/chat/conversations/${convId}/messages`, { method: "POST", body: JSON.stringify({ asset_id: asset.id, client_id: crypto.randomUUID() }) });
        onSent();
      } finally {
        setBusy(false);
      }
    };
    r.start();
    setRec(r);
  }

  return <Button type="button" variant="secondary" onClick={() => void toggle()} loading={busy}>{rec ? "Stop & send" : "🎤 Voice"}</Button>;
}
