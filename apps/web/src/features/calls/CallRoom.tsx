"use client";

import { Room, RoomEvent, Track, type RemoteTrack } from "livekit-client";
import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { Button } from "@/components/ui/Button";
import { ApiError, api } from "@/lib/api/client";
import styles from "@/features/ui.module.css";

interface CallToken { url: string; token: string; room: string }

/** 1:1 and small-group calls over LiveKit. Media flows browser <-> SFU; our API only issues 5-minute tokens. */
export function CallRoom({ conversationId, answering }: { conversationId: string; answering: boolean }) {
  const [state, setState] = useState<"connecting" | "live" | "ended" | "error">("connecting");
  const [error, setError] = useState<string | null>(null);
  const [muted, setMuted] = useState(false);
  const [cameraOff, setCameraOff] = useState(false);
  const localRef = useRef<HTMLVideoElement>(null);
  const remoteRef = useRef<HTMLDivElement>(null);
  const roomRef = useRef<Room | null>(null);

  useEffect(() => {
    let cancelled = false;
    const room = new Room({ adaptiveStream: true, dynacast: true });
    roomRef.current = room;
    const remoteBox = remoteRef.current;
    room.on(RoomEvent.TrackSubscribed, (track: RemoteTrack) => {
      if (!remoteBox) return;
      const el = track.attach();
      el.setAttribute("playsinline", "true");
      if (track.kind === Track.Kind.Video) el.style.width = "100%";
      remoteBox.appendChild(el);
    });
    room.on(RoomEvent.TrackUnsubscribed, (track: RemoteTrack) => track.detach().forEach((el) => el.remove()));
    room.on(RoomEvent.Disconnected, () => setState("ended"));
    (async () => {
      try {
        const t = await api<CallToken>(`/api/v1/calls/${conversationId}/token?ring=${answering ? "false" : "true"}`, { method: "POST" });
        if (cancelled) return;
        await room.connect(t.url, t.token);
        await room.localParticipant.enableCameraAndMicrophone();
        const cam = room.localParticipant.getTrackPublication(Track.Source.Camera)?.track;
        if (cam && localRef.current) cam.attach(localRef.current);
        setState("live");
      } catch (err) {
        if (cancelled) return;
        setState("error");
        setError(err instanceof ApiError ? err.message : "Could not start the call. Check camera/microphone permission.");
      }
    })();
    return () => {
      cancelled = true;
      void room.disconnect();
      remoteBox?.replaceChildren();
    };
  }, [conversationId, answering]);

  async function toggleMic() {
    await roomRef.current?.localParticipant.setMicrophoneEnabled(muted);
    setMuted(!muted);
  }

  async function toggleCamera() {
    await roomRef.current?.localParticipant.setCameraEnabled(cameraOff);
    setCameraOff(!cameraOff);
  }

  return (
    <section className={styles.card} aria-labelledby="call-title">
      <h1 id="call-title" className={styles.h2}>{state === "live" ? "On call" : state === "connecting" ? "Calling…" : state === "ended" ? "Call ended" : "Call failed"}</h1>
      {error ? <p className={styles.alert} role="alert">{error}</p> : null}
      <div ref={remoteRef} aria-label="Other participants" style={{ display: "grid", gap: "var(--space-2)" }} />
      <video ref={localRef} muted playsInline autoPlay aria-label="Your camera" style={{ width: 160, borderRadius: "var(--radius-control)", alignSelf: "end" }} />
      <div className={styles.nav}>
        <Button variant="secondary" onClick={() => void toggleMic()} disabled={state !== "live"}>{muted ? "Unmute" : "Mute"}</Button>
        <Button variant="secondary" onClick={() => void toggleCamera()} disabled={state !== "live"}>{cameraOff ? "Camera on" : "Camera off"}</Button>
        <Button variant="danger" onClick={() => void roomRef.current?.disconnect()}>End call</Button>
        <Link href={`/messages?c=${conversationId}`} className={styles.navLink}>Back to chat</Link>
      </div>
    </section>
  );
}
