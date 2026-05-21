import type { Metadata, Viewport } from "next";
import "./globals.css";
import { Providers } from "@/components/providers";
import { fontVariables } from "./fonts";
import { ViewToggle } from "@/components/scrapbook/view-toggle";

export const metadata: Metadata = {
  title: "Plus One — AI travel planner",
  description: "Local gems vs tourist traps, with sources you can verify.",
  manifest: "/manifest.json",
  appleWebApp: {
    capable: true,
    statusBarStyle: "default",
    title: "Plus One",
  },
};

export const viewport: Viewport = {
  themeColor: "#000000",
  width: "device-width",
  initialScale: 1,
  maximumScale: 1,
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body className={`${fontVariables} min-h-dvh`}>
        <Providers>
          {children}
          <ViewToggle />
        </Providers>
      </body>
    </html>
  );
}
