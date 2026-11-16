import type { Metadata } from "next";
import { Suspense } from "react";
import { TopBar } from "@/components/TopBar";
import { SearchResults } from "@/features/ai/SearchResults";
import styles from "@/features/ui.module.css";

export const metadata: Metadata = { title: "Search" };

export default function Page() {
  return (
    <main className={styles.shell}>
      <TopBar />
      <Suspense>
        <SearchResults />
      </Suspense>
    </main>
  );
}
