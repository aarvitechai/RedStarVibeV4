import type { Metadata } from "next";
import { Suspense } from "react";
import { LoginForm } from "@/features/auth/LoginForm";
import styles from "@/features/auth/auth.module.css";

export const metadata: Metadata = { title: "Log in" };

export default function LoginPage() {
  return (
    <main className={styles.page}>
      <Suspense>
        <LoginForm />
      </Suspense>
    </main>
  );
}
