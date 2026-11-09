import type { Metadata } from "next";
import type { ReactNode } from "react";
import "@suseelkrishna/fieryfusion-tokens/tokens.css";
import "@suseelkrishna/fieryfusion-tokens/fonts.css";
import "@suseelkrishna/fieryfusion-tokens/corporate.css";
import "@suseelkrishna/fieryfusion-react/styles.css";
import "./globals.css";

export const metadata: Metadata = {
  title: "RecruitAssist",
  description: "Ask your hiring pipeline anything. Every number comes from the data, every claim has a source.",
};

/** The root layout: the brand kit's styles with the light theme and the corporate profile. */
export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en" data-ff-theme="light" data-ff-profile="corporate">
      <body>{children}</body>
    </html>
  );
}
