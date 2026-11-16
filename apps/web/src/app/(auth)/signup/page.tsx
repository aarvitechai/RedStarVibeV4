import type { Metadata } from "next";
import { Suspense } from "react";
import { SignupForm } from "@/features/auth/SignupForm";
import styles from "@/features/auth/auth.module.css";

export const metadata: Metadata = { title: "Sign up" };

export default function SignupPage() {
  return (
    <main className={styles.page}>
      <Suspense>
        <SignupForm />
      </Suspense>
    </main>
  );
}
