import type { Metadata } from 'next';
import './globals.css';

export const metadata: Metadata = {
  title: 'repro-viewer — Paper 1 再現性実験ビューア',
  description: 'LLM パラメータ提案の再現性検証ログを閲覧・import するためのビューア',
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="ja" className="dark" suppressHydrationWarning>
      <head>
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="" />
        <link
          href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;600&display=swap"
          rel="stylesheet"
        />
      </head>
      <body className="min-h-dvh antialiased">{children}</body>
    </html>
  );
}
