import type { Metadata } from "next";
import "./globals.css";
import AppShell from "@/components/AppShell";
import { LanguageProvider } from "@/contexts/LanguageContext";

export const metadata: Metadata = {
  title: "明鉴 (MingJian) — Decision Intelligence",
  description: "AI-powered multi-agent platform for evidence-driven scenario simulation & strategic decision-making",
  icons: {
    icon: [
      { url: "/mingjian-icon.jpg", sizes: "192x192", type: "image/jpeg" },
      { url: "/favicon-icon.jpg", sizes: "512x512", type: "image/jpeg" },
    ],
    apple: [
      { url: "/mingjian-icon.jpg", sizes: "180x180", type: "image/jpeg" },
    ],
  },
  manifest: "/manifest.json",
};

export const viewport = {
  themeColor: "#09090b",
  width: "device-width",
  initialScale: 1,
  maximumScale: 1,
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="zh">
      <body className="min-h-screen">
        <LanguageProvider>
          <AppShell>{children}</AppShell>
        </LanguageProvider>
      </body>
    </html>
  );
}
