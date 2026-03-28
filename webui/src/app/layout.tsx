import type { Metadata } from "next";
import { JetBrains_Mono } from "next/font/google";
import "./globals.css";

const jetbrains = JetBrains_Mono({ subsets: ["latin"] });

export const metadata: Metadata = {
  title: "Marker PDF WebUI",
  description: "Dynamic SSE Progress Terminal",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className="dark">
      <body className={`${jetbrains.className} antialiased min-h-screen bg-zinc-950 text-zinc-50`}>
        {children}
      </body>
    </html>
  );
}
