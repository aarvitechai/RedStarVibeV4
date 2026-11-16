import Link from "next/link";
import { NearbySearch } from "@/features/business/NearbySearch";
import styles from "./page.module.css";

export default function HomePage() {
  return (
    <main className={styles.main}>
      <div className={styles.card}>
        <h1 className={styles.brand}>RedStarVibe</h1>
        <p className={styles.tagline}>Connect. Grow. Celebrate.</p>
        <p>Your business, one link away.</p>
        <nav className={styles.actions} aria-label="Account">
          <Link href="/signup" className={styles.primary}>Create your page</Link>
          <Link href="/login" className={styles.secondary}>Log in</Link>
          <Link href="/dashboard" className={styles.secondary}>My business</Link>
        </nav>
        <div style={{ marginTop: "var(--space-8)" }}>
          <NearbySearch />
        </div>
      </div>
    </main>
  );
}
