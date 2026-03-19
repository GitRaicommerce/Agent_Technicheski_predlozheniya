import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Prevent Next.js from 308-redirecting /api/v1/x/ → /api/v1/x
  // so rewrites forward the original URL (with trailing slash) directly to FastAPI
  skipTrailingSlashRedirect: true,
  async rewrites() {
    const apiUrl = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
    return [
      {
        source: "/api/v1/:path*",
        destination: `${apiUrl}/api/v1/:path*`,
      },
    ];
  },
};

export default nextConfig;
