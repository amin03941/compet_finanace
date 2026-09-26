import type { Metadata } from "next";
import "@fontsource-variable/inter";
import "@fontsource/ibm-plex-sans-arabic/400.css";
import "@fontsource/ibm-plex-sans-arabic/600.css";
import "./globals.css";
import { Shell } from "@/components/shell/shell";

export const metadata: Metadata = {
  title: "RASD 360 — Radar fiscal et douanier",
  description: "Prototype de ciblage fiscal et douanier (données entièrement fictives)",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="fr" suppressHydrationWarning>
      <body>
        <Shell>{children}</Shell>
      </body>
    </html>
  );
}
