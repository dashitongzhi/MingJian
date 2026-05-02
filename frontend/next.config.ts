import type { NextConfig } from "next";

const backendApiUrl =
  process.env.BACKEND_API_URL ||
  (process.env.NODE_ENV === "production" ? "http://api:8000" : "http://localhost:8000");

const nextConfig: NextConfig = {
  output: process.env.NEXT_OUTPUT === "export" ? "export" : "standalone",
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: `${backendApiUrl}/:path*`,
      },
    ];
  },
};

export default nextConfig;
