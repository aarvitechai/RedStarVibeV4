import Link from "next/link";
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
        </nav>
      </div>
    </main>
  );
}
