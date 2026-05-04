import type { NextConfig } from "next";

const backendApiUrl =
  process.env.BACKEND_API_URL ||
  (process.env.NODE_ENV === "production" ? "http://api:8000" : "http://127.0.0.1:8000");

const nextConfig: NextConfig = {
  output: process.env.NEXT_OUTPUT === "export" ? "export" : "standalone",
  devIndicators: false,
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: `${backendApiUrl}/:path*`,
      },
      {
        source: "/ws/:path*",
        destination: `${backendApiUrl}/ws/:path*`,
      },
    ];
  },
};

export default nextConfig;
