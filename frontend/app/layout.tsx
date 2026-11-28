import type { Metadata } from "next";
import localFont from "next/font/local";
import "./globals.css";
import "./workspace.css";

const bodyFont = localFont({
  src: [
    { path: "./fonts/BeVietnamPro-Regular.ttf", weight: "400", style: "normal" },
    { path: "./fonts/BeVietnamPro-Medium.ttf", weight: "500", style: "normal" },
    { path: "./fonts/BeVietnamPro-SemiBold.ttf", weight: "600", style: "normal" },
    { path: "./fonts/BeVietnamPro-Bold.ttf", weight: "700", style: "normal" },
  ],
  variable: "--font-body",
  display: "swap",
  preload: true,
});

export const metadata: Metadata = {
  title: "Mở — Học toán từ cách nghĩ",
  description: "Không gian học toán Socratic. Tự khám phá cách giải, nhận gợi ý và nhìn lại tiến bộ từng bước.",
  robots: { index: false, follow: false },
  icons: { icon: { url: "/brand/mo-classic-mark.svg", type: "image/svg+xml" } },
};

export default function Layout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="vi"><body className={bodyFont.variable}>{children}</body></html>;
}
