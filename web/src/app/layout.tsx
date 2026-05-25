import type { Metadata } from "next";
import { Instrument_Serif, IBM_Plex_Mono, IBM_Plex_Sans } from "next/font/google";
import { SiteHeader } from "@/components/site-header";
import { Providers } from "@/components/providers";
import { FaucetPrompt } from "@/components/faucet-prompt";
import "./globals.css";

const instrument = Instrument_Serif({
  weight: "400",
  subsets: ["latin"],
  variable: "--font-instrument",
});
const plexMono = IBM_Plex_Mono({
  weight: ["400", "500", "600"],
  subsets: ["latin"],
  variable: "--font-plex-mono",
});
const plexSans = IBM_Plex_Sans({
  weight: ["400", "500", "600"],
  subsets: ["latin"],
  variable: "--font-plex-sans",
});

export const metadata: Metadata = {
  metadataBase: process.env.VERCEL_URL
    ? new URL(`https://${process.env.VERCEL_URL}`)
    : new URL("http://localhost:3000"),
  title: "openmind — reasoning you can verify",
  description:
    "An autonomous prediction-market agent that builds a knowledge graph to find +EV bets, then anchors its reasoning trace on Arc and settles in USDC.",
  icons: {
    icon: "/logo.png",
    shortcut: "/logo.png",
    apple: "/logo.png",
  },
  openGraph: {
    title: "openmind — reasoning you can verify",
    description:
      "An autonomous prediction-market agent that builds a knowledge graph to find +EV bets, then anchors its reasoning trace on Arc and settles in USDC.",
    images: [{ url: "/logo.png", width: 512, height: 512, alt: "openmind" }],
  },
  twitter: {
    card: "summary",
    title: "openmind — reasoning you can verify",
    description:
      "An autonomous prediction-market agent that builds a knowledge graph to find +EV bets, then anchors its reasoning trace on Arc and settles in USDC.",
    images: ["/logo.png"],
  },
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body
        className={`${instrument.variable} ${plexMono.variable} ${plexSans.variable} grain scanlines min-h-screen antialiased`}
      >
        <Providers>
          <SiteHeader />
          <FaucetPrompt />
          <main className="relative z-10">{children}</main>
        </Providers>
      </body>
    </html>
  );
}
