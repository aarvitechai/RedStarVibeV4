"use client";

import { useState } from "react";
import { Button } from "@/components/ui/Button";
import { api } from "@/lib/api/client";
import styles from "@/features/ui.module.css";

/** Personal token for AI agents (MCP). Shown once; agents can read and save drafts, never publish or delete. */
export function McpTokens() {
  const [token, setToken] = useState<string | null>(null);
  async function create(scopes: string[]) {
    const r = await api<{ token: string }>("/api/v1/mcp-tokens", { method: "POST", body: JSON.stringify({ label: "AI agent", scopes }) });
    setToken(r.token);
  }
  return (
    <section className={styles.card} aria-labelledby="mcp-title">
      <h2 id="mcp-title" className={styles.h2}>Connect an AI agent (MCP)</h2>
      <p className={styles.muted}>Endpoint: /mcp. Tokens last 30 days. Agents can read your stats and save drafts; publishing always needs you.</p>
      <div className={styles.nav}>
        <Button size="sm" variant="secondary" onClick={() => void create(["read"])}>Read-only token</Button>
        <Button size="sm" variant="secondary" onClick={() => void create(["read", "write:drafts"])}>Token with drafts</Button>
      </div>
      {token ? <p className={styles.share}>Copy now — it will not be shown again: <code>{token}</code></p> : null}
    </section>
  );
}
