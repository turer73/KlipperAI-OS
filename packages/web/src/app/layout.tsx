import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "KlipperOS-AI Dashboard",
  description: "AI-powered 3D printer monitoring and control",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="tr" className="dark">
      <body className="min-h-screen antialiased">{children}</body>
    </html>
  );
}
