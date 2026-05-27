import type { Metadata } from "next";

import { AuthProvider } from "@/lib/auth-context";

import "./globals.css";

export const metadata: Metadata = {
  title: "NSK AI Labs — BharatPro AutoML",
  description:
    "AI-native AutoML platform by NSK AI Labs. Orchestrates five MCP microservices — dataset profiling, EDA, model training, explainability, and export.",
  keywords: ["AutoML", "MCP", "machine learning", "NSK AI Labs", "BharatPro", "data science"],
  authors: [{ name: "NSK AI Labs", url: "https://sites.google.com/nskailabs.com/nskailabs/home" }],
  icons: { icon: "/favicon.svg" },
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className="dark">
      <body className="min-h-screen">
        <AuthProvider>{children}</AuthProvider>
      </body>
    </html>
  );
}