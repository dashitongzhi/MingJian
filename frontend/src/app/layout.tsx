import type { Metadata } from "next";
import "./globals.css";
import AppShell from "@/components/AppShell";
import { ThemeProvider } from "@/components/ThemeProvider";
import { LanguageProvider } from "@/contexts/LanguageContext";
import { TooltipProvider } from "@/components/ui/tooltip";
import ErrorBoundary from "@/components/ErrorBoundary";
import { Toaster } from "sonner";
import { Geist } from "next/font/google";
import { cn } from "@/lib/utils";

const geist = Geist({ subsets: ["latin"], variable: "--font-sans" });

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
  themeColor: "#fafbfc",
  width: "device-width",
  initialScale: 1,
  maximumScale: 1,
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="zh" className={cn("font-sans", geist.variable)} suppressHydrationWarning>
      <body className="min-h-screen" suppressHydrationWarning>
        <ThemeProvider>
          <LanguageProvider>
            <TooltipProvider>
              <ErrorBoundary>
                <AppShell>{children}</AppShell>
              </ErrorBoundary>
              <Toaster position="top-center" richColors />
            </TooltipProvider>
          </LanguageProvider>
        </ThemeProvider>
      </body>
    </html>
  );
}
