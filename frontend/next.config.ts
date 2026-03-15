import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  turbopack: {
    // Force workspace root to frontend (avoid lockfile inference warning).
    root: process.cwd(),
  },
};

export default nextConfig;
