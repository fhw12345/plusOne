import {
  Caveat,
  Kalam,
  Special_Elite,
  Shippori_Mincho,
  Noto_Serif_JP,
  Plus_Jakarta_Sans,
} from "next/font/google";

export const fontHand = Caveat({
  subsets: ["latin"],
  weight: ["400", "500", "600", "700"],
  variable: "--font-hand",
  display: "swap",
});

export const fontHandAlt = Kalam({
  subsets: ["latin"],
  weight: ["400", "700"],
  variable: "--font-hand-alt",
  display: "swap",
});

export const fontType = Special_Elite({
  subsets: ["latin"],
  weight: ["400"],
  variable: "--font-type",
  display: "swap",
});

export const fontCjkSerif = Shippori_Mincho({
  subsets: ["latin"],
  weight: ["400", "500", "700"],
  variable: "--font-cjk-serif",
  display: "swap",
});

export const fontCjkSerifFallback = Noto_Serif_JP({
  subsets: ["latin"],
  weight: ["400", "500", "700"],
  variable: "--font-cjk-serif-fallback",
  display: "swap",
});

export const fontPrint = Plus_Jakarta_Sans({
  subsets: ["latin"],
  weight: ["400", "500", "600"],
  variable: "--font-print",
  display: "swap",
});

export const fontVariables = [
  fontHand.variable,
  fontHandAlt.variable,
  fontType.variable,
  fontCjkSerif.variable,
  fontCjkSerifFallback.variable,
  fontPrint.variable,
].join(" ");
