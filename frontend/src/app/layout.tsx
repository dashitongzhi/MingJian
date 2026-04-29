import type { Metadata } from "next";
import "./globals.css";
import Link from "next/link";

export const metadata: Metadata = {
  title: "PlanAgent — Decision Intelligence",
  description: "Multi-agent decision support and wargaming platform",
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
