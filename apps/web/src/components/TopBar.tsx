import Link from "next/link";
import styles from "@/features/ui.module.css";

export function TopBar() {
  return (
    <header className={styles.topbar}>
      <Link href="/" className={styles.brand}>RedStarVibe</Link>
      <nav className={styles.nav} aria-label="Main">
        <Link href="/feed" className={styles.navLink}>Feed</Link>
        <Link href="/reels" className={styles.navLink}>Reels</Link>
        <Link href="/messages" className={styles.navLink}>Messages</Link>
        <Link href="/bookings" className={styles.navLink}>My bookings</Link>
        <Link href="/orders" className={styles.navLink}>My orders</Link>
        <Link href="/dashboard" className={styles.navLink}>My business</Link>
        <Link href="/cards" className={styles.navLink}>Cards</Link>
        <Link href="/albums" className={styles.navLink}>Albums</Link>
        <Link href="/notifications" className={styles.navLink}>Notifications</Link>
        <Link href="/search" className={styles.navLink}>Search</Link>
        <Link href="/assistant" className={styles.navLink}>Assistant</Link>
        <Link href="/help" className={styles.navLink}>Help</Link>
        <Link href="/plans" className={styles.navLink}>Plans</Link>
        <Link href="/account" className={styles.navLink}>Account</Link>
      </nav>
    </header>
  );
}
