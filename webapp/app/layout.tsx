import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "PORTF.OS / INTELLIGENCE",
  description: "Quantitative portfolio intelligence for Indian equity markets",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body style={{ background: "#0a0a0a", height: "100vh", overflow: "hidden" }}>
        {children}
      </body>
    </html>
  );
}
