import type { Metadata } from "next";
import "./globals.css";
import Link from "next/link";

export const metadata: Metadata = {
  title: "PlanAgent — Decision Intelligence",
  description: "Multi-agent decision support and wargaming platform",
  icons: {
    icon: [
      { url: "/favicon-16x16.png", sizes: "16x16", type: "image/png" },
      { url: "/favicon-32x32.png", sizes: "32x32", type: "image/png" },
      { url: "/icon-192.png", sizes: "192x192", type: "image/png" },
      { url: "/icon-512.png", sizes: "512x512", type: "image/png" },
    ],
    apple: [
      { url: "/apple-touch-icon.png", sizes: "180x180", type: "image/png" },
    ],
    other: [
      {
        rel: "mask-icon",
        url: "/icon.svg",
        color: "#4F46E5",
      },
    ],
  },
  manifest: "/manifest.json",
};

export const viewport = {
  themeColor: "#4F46E5",
  width: "device-width",
  initialScale: 1,
  maximumScale: 1,
};

const NAV = [
  { href: "/", label: "Dashboard" },
  { href: "/assistant", label: "Strategic Assistant" },
  { href: "/simulation", label: "Simulation" },
  { href: "/debate", label: "Debate Center" },
  { href: "/evidence", label: "Intelligence" },
];

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="min-h-screen">
        <nav className="border-b border-[var(--card-border)] bg-[var(--card)]">
          <div className="max-w-[1600px] mx-auto flex items-center gap-6 px-6 h-12">
            <span className="font-bold text-sm tracking-wide">PLANAGENT</span>
            {NAV.map((item) => (
              <Link key={item.href} href={item.href} className="text-sm text-[var(--muted)] hover:text-[var(--foreground)] transition-colors">
                {item.label}
              </Link>
            ))}
          </div>
        </nav>
        <main className="max-w-[1600px] mx-auto p-6">{children}</main>
      </body>
    </html>
  );
}
