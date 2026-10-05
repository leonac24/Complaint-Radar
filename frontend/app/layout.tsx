import type { Metadata } from "next";
import type { ReactNode } from "react";
import "./globals.css";

export const metadata: Metadata = {
  title: "Complaint Radar",
  description:
    "An early-warning radar for consumer finance risk, built on the CFPB complaint narratives archive.",
};

const FONTS =
  "https://fonts.googleapis.com/css2?family=Familjen+Grotesk:wght@400;500;600;700&family=Spectral:wght@400;500;600&family=Martian+Mono:wght@400;500&display=swap";

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <head>
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="" />
        <link rel="stylesheet" href={FONTS} />
      </head>
      <body>{children}</body>
    </html>
  );
}
