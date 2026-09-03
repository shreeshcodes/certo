import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Certo | Continuous Compliance",
  description: "AI-native continuous compliance for multi-state US fintech lending.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
