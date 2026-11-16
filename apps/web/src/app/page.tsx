import styles from "./page.module.css";

export default function HomePage() {
  return (
    <main className={styles.main}>
      <div className={styles.card}>
        <h1 className={styles.brand}>RedStarVibe</h1>
        <p className={styles.tagline}>Connect. Grow. Celebrate.</p>
        <p>Your business, one link away.</p>
        <span className={styles.status}>Phase 0 — platform foundation</span>
      </div>
    </main>
  );
}
