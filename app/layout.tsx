import type { Metadata } from "next";
import "@fontsource/cairo/400.css";
import "@fontsource/cairo/600.css";
import "@fontsource/cairo/700.css";
import "@fontsource/cairo/800.css";
import "@fontsource/cairo/900.css";
import "./globals.css";

export const metadata: Metadata = {
  title: "الباحثة القانونية الذكية",
  description:
    "محرك بحث سعودي موحّد للأحكام والسوابق والقرارات والمبادئ القضائية والتعاميم مع عدادات موثقة من السجلات الفريدة.",
  icons: {
    icon: "/favicon.svg",
    shortcut: "/favicon.svg",
  },
  other: {
    "codex-preview": "development",
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="ar" dir="rtl">
      <body>{children}</body>
    </html>
  );
}
