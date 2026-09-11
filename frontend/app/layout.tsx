import type { Metadata } from "next";
import { Inter } from "next/font/google";
import Link from "next/link";
import { Boxes } from "lucide-react";
import "./globals.css";

const inter = Inter({ subsets: ["latin"], variable: "--font-inter" });

export const metadata: Metadata = {
  title: "Supply Chain Risk Monitor | FMN",
  description:
    "Identify SKUs likely to require attention before inventory becomes a problem.",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" className={inter.variable}>
      {/* Page gradient and horizontal-overflow containment live in globals.css. */}
      <body className="min-h-screen font-sans antialiased">
        <header className="sticky top-0 z-20 border-b border-slate-200/80 backdrop-blur-md [background:var(--grad-header)]">
          <div className="mx-auto flex h-14 max-w-[1400px] items-center justify-between px-4 sm:px-6">
            <Link
              href="/supply-chain"
              className="group flex items-center gap-2.5"
            >
              <span className="grad-brand flex h-7 w-7 items-center justify-center rounded-lg shadow-sm ring-1 ring-inset ring-white/20 transition-shadow group-hover:shadow-md">
                <Boxes className="h-4 w-4 text-white" />
              </span>
              <span className="text-sm font-semibold text-slate-900">
                Supply Chain Risk Monitor
              </span>
            </Link>
            <nav className="flex items-center gap-1 text-sm">
              <Link
                href="/supply-chain"
                className="rounded-md px-3 py-1.5 text-slate-600 transition-colors hover:bg-white/70 hover:text-slate-900"
              >
                Dashboard
              </Link>
              <Link
                href="/supply-chain/model"
                className="rounded-md px-3 py-1.5 text-slate-600 transition-colors hover:bg-white/70 hover:text-slate-900"
              >
                How it works
              </Link>
            </nav>
          </div>
          {/* Hairline gradient rule: separates the header without a hard border. */}
          <div className="grad-brand h-px w-full opacity-30" />
        </header>
        <main className="mx-auto max-w-[1400px] px-4 py-6 sm:px-6">
          {children}
        </main>
      </body>
    </html>
  );
}
