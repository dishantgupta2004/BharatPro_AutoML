import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Unisole Empower — Distributed AutoML",
  description:
    "Enterprise AutoML copilot orchestrating five MCP microservices. Upload data, chat in plain English, ship models.",
  icons: {
    icon: "/favicon.svg",
  },
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className="dark">
      <body className="min-h-screen">{children}</body>
    </html>
  );
}