import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  output: "standalone",
  poweredByHeader: false,
  reactStrictMode: true,
  // Images are pre-sized AVIF/WebP from the media worker and rendered with <picture> (ADR 0004).
  images: { unoptimized: true },
};

export default nextConfig;
