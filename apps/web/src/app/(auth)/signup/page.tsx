import type { Metadata } from "next";
import { SignupForm } from "@/features/auth/SignupForm";
import styles from "@/features/auth/auth.module.css";

export const metadata: Metadata = { title: "Sign up" };

export default function SignupPage() {
  return (
    <main className={styles.page}>
      <SignupForm />
    </main>
  );
}
