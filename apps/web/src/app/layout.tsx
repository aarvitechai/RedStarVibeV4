import type { Metadata, Viewport } from "next";
import { headers } from "next/headers";
import type { ReactNode } from "react";
import "@/styles/globals.css";

export const metadata: Metadata = {
  title: { default: "RedStarVibe", template: "%s · RedStarVibe" },
  description: "Your business, one link away. Pages, bookings, orders and a local social feed in one place.",
  applicationName: "RedStarVibe",
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  themeColor: "#C8102E",
};

export default async function RootLayout({ children }: { children: ReactNode }) {
  // Reading the request headers makes every page render per request, so Next.js can stamp
  // the CSP nonce set in src/proxy.ts onto its scripts. Static pages would be blocked by the CSP.
  await headers();
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
