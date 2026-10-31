import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "RoboSkills × BluPe · Two arms, working together",
  description: "Explore, run and review RoboSkills with bimanual YAM arms.",
  icons: {
    icon: "/favicon.svg",
    shortcut: "/favicon.svg",
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body className="antialiased">{children}</body>
    </html>
  );
}
